# Bonsai Connector

This package contains a bonsai connector, which allows to easily connect
python simulations to Bonsai.


## Usage

Simply install the package with

```sh
pip install 'git+https://github.com/mzat-msft/bonsai-connector/'
```

Then you can connect to the platform as follows:

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
```

You must provide and interface dictionary when initializing the connector. At
each step of the loop the platform will send an event to the sim, such as
start an episode, take a step, end an episode. These event will trigger the
corresponding action from the simulation class.
