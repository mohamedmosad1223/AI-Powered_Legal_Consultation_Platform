from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import uvicorn
import sys

# Reconfigure stdout for Arabic characters on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from src.controllers.ingestion import IngestionController
from src.controllers.graph_viewer import GraphViewerController
from src.controllers.rag_controller import RAGController
from pydantic import BaseModel

app = FastAPI(title="Legal AI Platform")

# Paths configuration
base_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(base_dir, "views", "static")
templates_dir = os.path.join(base_dir, "views", "templates")

# Mount Static Files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Jinja2 Templates
templates = Jinja2Templates(directory=templates_dir)

class QueryRequest(BaseModel):
    query: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Renders main interactive graph explorer dashboard."""
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/rag", response_class=HTMLResponse)
async def read_rag(request: Request):
    """Renders RAG Assistant page."""
    return templates.TemplateResponse(request=request, name="rag.html")

@app.post("/api/rag/query")
async def rag_query(request: QueryRequest):
    """Processes RAG query and returns generated answer with sources."""
    try:
        controller = RAGController()
        result = controller.query(request.query)
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/graph/laws")
async def get_laws():
    """
    Returns only Law nodes — the root of the expand-on-click tree.
    """
    controller = GraphViewerController()
    return controller.get_laws()

@app.get("/api/graph/children")
async def get_children(
    node_id: str = Query(..., description="Property ID of the node to expand"),
    node_type: str = Query(..., description="Type label: Law | LawVersion | ArticleVersion | Paragraph"),
):
    """
    Returns direct children of a given node for expand-on-click tree.
    """
    controller = GraphViewerController()
    return controller.get_children(node_id, node_type)

@app.post("/api/ingest")
async def trigger_ingest():
    """Endpoint triggering document parsing and database ingestion."""
    try:
        controller = IngestionController()
        controller.run_ingestion()
        return {"status": "success", "message": "Ingestion completed successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    uvicorn.run("src.app:app", host="127.0.0.1", port=8000, reload=True)
