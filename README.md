# Bonsai Connector

This package contains a bonsai connector, which allows to easily connect
python simulations to Bonsai.


## Usage

Simply install the package with

```sh
pip install -e 'git+https://github.com/mzat-msft/bonsai-connector?#egg=bonsai_connector'
```

Then you can use the connector in two ways, either by creating a connector
instance and use it to communicate with Bonsai, or by using the connector as a
context manager. The difference between the two method is that the context
manager takes care of closing the connection to the platform as soon as the
sim shuts down, while in the other case you have to close the connection
yourself.
The following code snippet shows how to use the connector without leveraging
its context manager capabilities:

```python
from bonsai_connector import BonsaiConnector

class SomeSim:
    def __init__(self):
        interface = {"name": "My simulation"}
        self.connector = BonsaiConnector(interface)

    def run_sym(self):
        while True:
            next_event = self.connector.next_event(self.state)
            self.do_something_with_event(next_event)
        # Close the connection after you're done
        self.connector.close_connection()
```

You must provide an interface dictionary when initializing the connector. At
each step of the loop the platform will send an event to the sim, such as
start an episode, take a step, end an episode. These event will trigger the
corresponding action from the simulation class.

### Unregister events

In case of unregister events sent by Bonsai, you can choose whether to let
the sim reconnect to the platform or just gracefully exit.
This choice is made when initializing the connector by setting the value of
the ``retry`` parameter. When it is set to `True`, the connector reconnects
the sim. By default `retry` is set to `False`.
