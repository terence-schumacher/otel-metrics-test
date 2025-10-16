"""
FastAPI Application with OpenTelemetry Metrics Export

This application demonstrates comprehensive OTel instrumentation with:
- Automatic HTTP request/response metrics
- Custom business metrics
- OTLP export to collector on localhost:4318
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn
import time
import random
import os

# OpenTelemetry imports
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.metrics import get_meter_provider, set_meter_provider

# Configuration - Read from environment
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "fastapi-otel-demo")
# CRITICAL: For HTTP, use the full path. For gRPC, use just host:port
# The Python HTTP exporter needs the full URL including /v1/metrics
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

# Fix the endpoint - ensure it has /v1/metrics for HTTP
if OTLP_ENDPOINT and not OTLP_ENDPOINT.endswith('/v1/metrics'):
    OTLP_ENDPOINT = f"{OTLP_ENDPOINT}/v1/metrics"


# Initialize OpenTelemetry
def init_telemetry():
    """Initialize OpenTelemetry with OTLP exporter"""
    resource = Resource.create({
        "service.name": SERVICE_NAME,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENVIRONMENT", "development")
    })

    # Configure OTLP HTTP exporter with full endpoint
    exporter = OTLPMetricExporter(
        endpoint=OTLP_ENDPOINT,
        timeout=10
    )

    # Create metric reader with 10s export interval
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10000)

    # Set up MeterProvider
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    set_meter_provider(provider)

    return provider


# Initialize telemetry
meter_provider = init_telemetry()
meter = metrics.get_meter(__name__)

# Custom metrics
request_counter = meter.create_counter(
    name="custom.requests.total",
    description="Total number of requests by endpoint",
    unit="1"
)

processing_time = meter.create_histogram(
    name="custom.processing.duration",
    description="Processing duration for business logic",
    unit="ms"
)

active_connections = meter.create_up_down_counter(
    name="custom.active.connections",
    description="Number of active connections",
    unit="1"
)


# Pydantic models
class Item(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    tax: Optional[float] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: float


# Initialize FastAPI
app = FastAPI(
    title="OTel Instrumented API",
    description="FastAPI with OpenTelemetry metrics collection",
    version="1.0.0"
)

# Instrument FastAPI - ONLY for metrics, disable traces
# We're not setting up trace exporters, so disable automatic trace instrumentation
FastAPIInstrumentor.instrument_app(app)


# Middleware for connection tracking
@app.middleware("http")
async def track_connections(request: Request, call_next):
    active_connections.add(1, {"endpoint": request.url.path})
    try:
        response = await call_next(request)
        return response
    finally:
        active_connections.add(-1, {"endpoint": request.url.path})


# In-memory storage for demo
items_db = {}


# Endpoints
@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information"""
    request_counter.add(1, {"endpoint": "/", "method": "GET"})
    return {
        "service": SERVICE_NAME,
        "version": "1.0.0",
        "metrics_endpoint": OTLP_ENDPOINT,
        "available_endpoints": [
            "GET /",
            "GET /health",
            "GET /items",
            "POST /items",
            "GET /items/{item_id}",
            "PUT /items/{item_id}",
            "DELETE /items/{item_id}",
            "GET /simulate/slow",
            "GET /simulate/error"
        ]
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    request_counter.add(1, {"endpoint": "/health", "method": "GET"})
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
        timestamp=time.time()
    )


@app.get("/items", response_model=dict)
async def list_items():
    """List all items"""
    start = time.time()
    request_counter.add(1, {"endpoint": "/items", "method": "GET"})

    # Simulate processing
    time.sleep(random.uniform(0.01, 0.05))

    duration = (time.time() - start) * 1000
    processing_time.record(duration, {"endpoint": "/items", "method": "GET"})

    return {"items": list(items_db.values()), "count": len(items_db)}


@app.post("/items", response_model=Item, status_code=201)
async def create_item(item: Item):
    """Create a new item"""
    start = time.time()
    request_counter.add(1, {"endpoint": "/items", "method": "POST"})

    item_id = str(len(items_db) + 1)
    item_dict = item.dict()
    item_dict["id"] = item_id
    items_db[item_id] = item_dict

    duration = (time.time() - start) * 1000
    processing_time.record(duration, {"endpoint": "/items", "method": "POST"})

    return item_dict


@app.get("/items/{item_id}", response_model=dict)
async def get_item(item_id: str):
    """Get a specific item by ID"""
    start = time.time()
    request_counter.add(1, {"endpoint": "/items/{item_id}", "method": "GET"})

    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    duration = (time.time() - start) * 1000
    processing_time.record(duration, {"endpoint": "/items/{item_id}", "method": "GET"})

    return items_db[item_id]


@app.put("/items/{item_id}", response_model=dict)
async def update_item(item_id: str, item: Item):
    """Update an existing item"""
    start = time.time()
    request_counter.add(1, {"endpoint": "/items/{item_id}", "method": "PUT"})

    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    item_dict = item.dict()
    item_dict["id"] = item_id
    items_db[item_id] = item_dict

    duration = (time.time() - start) * 1000
    processing_time.record(duration, {"endpoint": "/items/{item_id}", "method": "PUT"})

    return item_dict


@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: str):
    """Delete an item"""
    start = time.time()
    request_counter.add(1, {"endpoint": "/items/{item_id}", "method": "DELETE"})

    if item_id not in items_db:
        raise HTTPException(status_code=404, detail="Item not found")

    del items_db[item_id]

    duration = (time.time() - start) * 1000
    processing_time.record(duration, {"endpoint": "/items/{item_id}", "method": "DELETE"})

    return None


@app.get("/simulate/slow")
async def simulate_slow():
    """Simulate a slow endpoint for testing latency metrics"""
    start = time.time()
    request_counter.add(1, {"endpoint": "/simulate/slow", "method": "GET"})

    # Random delay between 1-3 seconds
    delay = random.uniform(1, 3)
    time.sleep(delay)

    duration = (time.time() - start) * 1000
    processing_time.record(duration, {"endpoint": "/simulate/slow", "method": "GET"})

    return {"message": "Slow response", "delay_seconds": delay}


@app.get("/simulate/error")
async def simulate_error():
    """Simulate errors for testing error rate metrics"""
    request_counter.add(1, {"endpoint": "/simulate/error", "method": "GET"})

    # 50% chance of error
    if random.random() < 0.5:
        raise HTTPException(status_code=500, detail="Simulated internal server error")

    return {"message": "Success!"}


if __name__ == "__main__":
    print(f"🚀 Starting {SERVICE_NAME}")
    print(f"📊 Exporting metrics to: {OTLP_ENDPOINT}")
    print(f"🌐 API available at: http://localhost:8000")
    print(f"📖 API docs at: http://localhost:8000/docs")

    uvicorn.run(app, host="0.0.0.0", port=8000)