# Defer LLM Orchestration Framework

For the first live LLM-backed component, the **Question Interpreter** will use
direct OpenAI SDK integration behind a provider boundary rather than adopting
LangChain or LangGraph. This keeps the first live provider small and preserves
the existing **Workflow Orchestrator**, **Semantic Router**, **Data Requester**,
and **Access Controller** boundaries while leaving room to choose LangChain or
LangGraph before adding a second LLM-backed component or stateful conversation
flow.
