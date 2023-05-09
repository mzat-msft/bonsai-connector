import dataclasses
import json
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Union

import jsonschema
from jsonschema.exceptions import ValidationError
from microsoft_bonsai_api.simulator.client import BonsaiClient, BonsaiClientConfig
from microsoft_bonsai_api.simulator.generated.models import (
    SimulatorInterface,
    SimulatorState,
)

from bonsai_connector.logger import log


class BonsaiEventType(Enum):
    IDLE = "Idle"
    EPISODE_START = "EpisodeStart"
    EPISODE_STEP = "EpisodeStep"
    EPISODE_FINISH = "EpisodeFinish"


@dataclasses.dataclass
class BonsaiEvent:
    event_type: BonsaiEventType
    event_content: Optional[Dict[str, Union[str, dict]]]

    def __repr__(self):
        return f"{self.event_type}: {self.event_content}"


def validate_state(state):
    """
    Validate the state.

    The serialization of the state works only on builtin types.
    """
    allowed_types = (bool, dict, float, int, list)
    iterable_types = (dict, list)

    def has_invalid_type(x):
        """
        Return False when x is not an allowed type.

        We need to use ``type`` instead of ``isinstance`` because of:
        https://github.com/Azure/msrest-for-python/issues/257
        """
        return type(x) not in allowed_types

    if has_invalid_type(state):
        raise TypeError(f"Element '{state}' not supported: {type(state)}")

    if not has_invalid_type(state) and type(state) not in iterable_types:
        return

    if type(state) == dict:
        # Assume key is always a supported type
        for _, val in state.items():
            validate_state(val)
    elif type(state) == list:
        for item in state:
            validate_state(item)


class BonsaiConnector:
    """
    Class that allows communications between Bonsai and Simulation.

    The class initialized by passing the simulation interface as a
    JSON-serializable dictionary. The dictionary must contain the ``name`` of
    the sim and the ``timeout`` in seconds as an ``int``.

    Parameters
    ----------

    sim_interface : dict
        Dictionary containing simulator informations such as ``name`` and ``timeout``

    retry : bool
        If true, when platform unregisters the sim the connector tries to reconnect

    verbose : bool
        Higher level of verbosity for logs
    """

    def __init__(self, sim_interface, *, retry=False, verbose=False):
        self.client_config = BonsaiClientConfig(enable_logging=verbose)
        self.workspace = self.client_config.workspace
        self.client = BonsaiClient(self.client_config)
        self.verbose = verbose
        self.sim_interface = self.validate_interface(sim_interface)
        self.retry = retry
        self.register_sim()

    def validate_interface(self, sim_interface):
        schema_loc = Path(__file__).parent / "schema"

        schema_iface = json.loads((schema_loc / "siminterface.schema.json").read_text())

        schema_types_fp = schema_loc / "simtypes.schema.json"
        schema_types = json.loads(schema_types_fp.read_text())
        schema_store = {
            str(f'/{schema_types_fp.name}'): schema_types,
        }

        resolver = jsonschema.RefResolver.from_schema(schema_iface, store=schema_store)
        try:
            jsonschema.validate(sim_interface, schema_iface, resolver=resolver)
            log.info("JSON schema for sim_interface successfully validated.")
        except ValidationError as exc:
            log.warning("Errors validating sim_interface JSON schema.")
            log.warning(exc)
        except BaseException as exc:
            log.warning("Something went wrong when validating sim_interface schema.")
            log.warning(exc)
        return sim_interface

    def __enter__(self):
        return self

    def __exit__(self, type_, value, traceback):
        log.info(
            f"Closing session with session_id {self.registered_session.session_id}"
        )
        self.close_session()
        if type_ == KeyboardInterrupt:
            return True

    def register_sim(self):
        reg_info = SimulatorInterface(
            simulator_context=self.client_config.simulator_context,
            **self.sim_interface,
        )
        self.registered_session = self.client.session.create(
            workspace_name=self.workspace,
            body=reg_info,
        )
        self.sequence_id = 1
        log.info(
            f"Created session with session_id {self.registered_session.session_id}"
        )

    def next_event(self, state) -> BonsaiEvent:
        """Poll the Bonsai platform for the next event and advance the state."""
        validate_state(state)
        sim_state = SimulatorState(
            sequence_id=self.sequence_id,
            state=state,
            halted=state.get("halted", False),
        )
        event = self.client.session.advance(
            workspace_name=self.workspace,
            session_id=self.registered_session.session_id,
            body=sim_state,
        )
        self.sequence_id = event.sequence_id
        if event.type == "Idle":
            log.info("Idling...")
            return BonsaiEvent(BonsaiEventType.IDLE, {})
        elif event.type == "EpisodeStart":
            log.info("Start episode")
            return BonsaiEvent(
                BonsaiEventType.EPISODE_START, event.episode_start.config
            )
        elif event.type == "EpisodeStep":
            log.info("Episode step")
            return BonsaiEvent(BonsaiEventType.EPISODE_STEP, event.episode_step.action)
        elif event.type == "EpisodeFinish":
            log.info("Finish step")
            return BonsaiEvent(
                BonsaiEventType.EPISODE_FINISH, event.episode_finish.reason
            )
        elif event.type == "Unregister":
            log.info("Simulator Session unregistered by the platform")
            if self.retry:
                log.info("Re-registering...")
                self.register_sim()
                self.next_event(state)
            else:
                raise RuntimeError(
                    "Simulator Session unregistered by platform because of ",
                    event.unregister.details,
                )
        raise TypeError(f"Unknown event type. Received {event.type}")

    def close_session(self):
        """Unregister gracefully the sim from Bonsai."""
        log.debug("Closing session...")
        self.client.session.delete(
            workspace_name=self.workspace,
            session_id=self.registered_session.session_id,
        )
