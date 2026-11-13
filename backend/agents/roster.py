"""Agent roster rendered by the frontend's Agent Mesh screen."""

AGENTS = [
    {
        "id": "supervisor",
        "name": "Supervisor",
        "role": "Coordinator",
        "stage": 1,
        "description": "Reads the request and conversation, sets intent, decomposes the task and assigns specialists.",
        "tools": ["conversation memory", "intent router", "task planner"],
    },
    {
        "id": "research",
        "name": "Research",
        "role": "Evidence gatherer",
        "stage": 2,
        "description": "Rewrites the query, searches the 1,054-page DGMS corpus with FAISS and reranks the passages.",
        "tools": ["FAISS index", "all-MiniLM-L6-v2", "cross-encoder rerank"],
    },
    {
        "id": "analysis",
        "name": "Analysis",
        "role": "Hazard analyst",
        "stage": 3,
        "description": "Classifies the hazard against a mining taxonomy and extracts severity drivers and incident signals.",
        "tools": ["hazard taxonomy", "severity rules"],
    },
    {
        "id": "compliance",
        "name": "Compliance",
        "role": "Statutory reviewer",
        "stage": 4,
        "description": "Maps the findings to statutory checks and control measures, flagging what must be verified on site.",
        "tools": ["DGMS checklists", "control library"],
    },
    {
        "id": "report",
        "name": "Report",
        "role": "Writer",
        "stage": 5,
        "description": "Composes the cited answer or audit narrative from the shared state, never from outside the evidence.",
        "tools": ["structured synthesis", "citation builder"],
    },
    {
        "id": "critic",
        "name": "Critic",
        "role": "Verifier",
        "stage": 6,
        "description": "Checks grounding and coverage; sends the run back to research when evidence is too thin.",
        "tools": ["grounding check", "coverage threshold", "replan trigger"],
    },
]

PIPELINE = [
    "Supervisor",
    "Research",
    "Analysis",
    "Compliance",
    "Report",
    "Critic",
]
