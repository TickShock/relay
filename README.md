# relay

**The Gateway to Global Markets.**

`relay` is the API integration layer for the TickShock ecosystem, abstracting brokerage-specific logic into a standardized interface.

---

### 📦 Key Features

* **Provider Abstraction:** Normalizes multiple brokerage APIs into a unified interface.
* **Order Routing:** Translates signals from **[arc](https://github.com/TickShock/arc)** into provider-specific executions.
* **Type Safety:** Uses **[ground](https://github.com/TickShock/ground)** to ensure schema consistency across all integrations.
* **Monitoring:** Streams connectivity metrics directly to **[gauge](https://github.com/TickShock/gauge)**.

### 🚀 Quick Start

Add to your `pyproject.toml`:

```toml
[tool.poetry.dependencies]
relay = { git = "https://github.com/TickShock/relay", tag = "v0.1.0" }

Reference relay content:

```
from tickshock.relay.liquid import Liquid
```
