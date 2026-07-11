# Concierge Agent: The Hyper-Local Itinerary Scraper

An intelligent agent built with the **Agent Development Kit (ADK)** and Google Gemini to orchestrate hyper-local weekend planning. The agent queries real-time weather forecasts, scrapes local HTML calendars using BeautifulSoup, and schedules a sequential Saturday itinerary under a requested budget, automatically routing based on weather conditions (e.g., omitting outdoor activities during rain).

---

## 📂 Project Structure

```
concierge-agent/
├── app/
│   ├── agent.py               # Root agent config & system instruction
│   ├── tools.py               # Weather geocoding/forecast, BeautifulSoup scraper, and scheduling filters
│   └── fast_api_app.py        # FastAPI server interface
├── tests/
│   ├── integration/
│   │   └── test_agent.py      # Stream and logic integration tests
│   └── eval/
│       ├── datasets/
│       │   └── itinerary-dataset.json # Seattle & Phoenix evaluation cases
│       ├── eval_config.yaml   # Local evaluation metrics config
│       ├── metrics.py         # Response quality metric (LLM-as-judge)
│       └── itinerary_metric.py# Custom deterministic budget/weather constraint checker
├── run_offline_inference.py   # Offline inference trace generator
├── GEMINI.md                  # Development guidance reference
├── pyproject.toml             # Dependencies (google-adk, beautifulsoup4, requests)
└── README.md                  # This file
```

---

## 🛠️ Built-in Tools

The agent leverages three core tools implemented in `app/tools.py`:

1. **`get_weather_forecast(city: str) -> dict`**:
   - Geocodes the city name via Open-Meteo's API.
   - Fetches the upcoming Saturday's daily forecast (maximum temperature, rain probability, and WMO weather codes).
2. **`scrape_public_events(url: str, city: str) -> dict`**:
   - Uses `BeautifulSoup` to parse HTML event calendar pages.
   - Fallbacks to deterministic mock event tables for testing target evaluation cities (Seattle and Phoenix).
3. **`filter_and_schedule_itinerary(events: list, weather_condition: str, budget: float) -> dict`**:
   - Filters out outdoor events if `weather_condition` is `"Rain"`.
   - Ensures total event costs stay strictly within the user's budget.
   - Greedily schedules events sequentially (9:00 AM – 9:00 PM) to avoid overlapping time conflicts.

---

## 💡 Quick Start & Local Commands

### Prerequisites
Make sure you have `uv` installed. Add your API key to `.env`:
```env
GEMINI_API_KEY=your-api-key-here
```

### 1. Install Dependencies
```bash
agents-cli install
```

### 2. Run Interactive Planning CLI
Ask the agent to plan an itinerary:
```bash
agents-cli run "Plan a cheap Saturday in Seattle"
```

### 3. Launch Web Playground
Start the local FastAPI server and open the ADK developer playground:
```bash
agents-cli playground
```
Once started, access the UI at **[http://127.0.0.1:8080/dev-ui/?app=app](http://127.0.0.1:8080/dev-ui/?app=app)**.

### 4. Run Evaluation Suite
Generate traces locally and grade them against the LLM judge and logic checker:
```bash
# Generate trace file
uv run python3 run_offline_inference.py

# Grade the trace file
agents-cli eval grade --traces artifacts/traces/traces.json --config tests/eval/eval_config.yaml
```

---

## 🧪 Verification & Evals

The agent is validated using:
- **`pytest`**: Automated streaming integration check (`pytest tests/integration/test_agent.py`).
- **`itinerary_correctness`**: A deterministic parser check confirming budget limits (`cost <= budget`) and rainy weather outdoor filtering (`no outdoor activities if Rain`).
- **`custom_response_quality`**: An LLM-as-judge rating that scores formatting, clarity, and calendar inclusion details (1-5 scale).
