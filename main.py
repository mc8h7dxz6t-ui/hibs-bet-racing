from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os

app = FastAPI(title="HIBS Racing")

class PredictionRequest(BaseModel):
    source: str = "hibs_base44"

class HorsePrediction(BaseModel):
    race_id: str
    horse_name: str
    horse_id: Optional[str] = ""
    bet_type: str = "ew"
    stake_win: float = 1.0
    stake_place: float = 1.0
    offered_win_price: float
    offered_place_price: float
    place_terms_denom: int = 5
    place_positions: int = 3
    engine_profile: str = "python_ml"
    config_hash: str
    steam_gate: str = "unknown"
    data_quality_pct: Optional[float] = None
    place_ev: Optional[float] = None
    combo_bayes_place: Optional[float] = None
    gate1_pass: bool = False
    gate2_pass: bool = False
    value_gate_reason: str = ""
    shadow_intent: bool = False
    exchange_sp_premium_delta: Optional[float] = None
    notes: str = ""

@app.post("/")
async def get_predictions(request: PredictionRequest):
    try:
        return []
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
