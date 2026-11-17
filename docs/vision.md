# Mantle AI

## Project Vision

Build **Mantle AI**, a developer-focused AI engineering workspace that helps developers build software more effectively by solving practical problems they face while working with LLMs, AI coding tools, and modern software development workflows.

**Mantle AI is NOT an LLM model.**  
We are building a software product that developers can install and use to work with multiple LLMs, maintain context, understand software fundamentals, plan projects, write and improve code, and follow a structured software-engineering workflow.

The goal is to make AI-assisted development feel less like random "vibe coding" and more like working with an experienced software engineering team.

---

## Core Problems Mantle AI Should Solve

### 1. Seamless LLM Switching

Developers often work with one LLM and suddenly hit:

- token/context limits
- rate limits
- model availability issues
- quality limitations
- expensive usage
- provider-specific restrictions

Currently, switching to another model often means manually copying the conversation, code, requirements, errors, and previous context.

**Mantle AI should solve this.**

A developer should be able to switch between supported LLMs without manually rebuilding the entire context.

For example:

```text
Developer is working with Model A
        ↓
Context + project state + conversation history
        ↓
Model A reaches its limit / becomes unsuitable
        ↓
Developer selects Model B
        ↓
Mantle reconstructs the required context
        ↓
Developer continues working
```

The user should feel like they are continuing the same development session rather than starting over.

---

# 2. Structured AI-Assisted Software Development

Mantle AI should help developers go beyond simply generating code.

A developer should be able to take an idea and progressively move through:

```text
Idea
 ↓
Requirements
 ↓
Architecture
 ↓
Tech Stack
 ↓
Database Design
 ↓
API Design
 ↓
Implementation
 ↓
Testing
 ↓
Debugging
 ↓
Security
 ↓
Deployment
 ↓
Monitoring
 ↓
Scaling
```

Mantle should explain **what needs to be done, why it is needed, and how to implement it.**

---

# 3. A-Z Software Engineering Guidance

One major problem with AI-assisted/vibe coding is that developers can generate working code without understanding the engineering concepts behind it.

Mantle AI should help bridge that gap.

For example, when a developer is building a backend application, Mantle should be able to explain relevant concepts such as:

- HTTP
- REST APIs
- authentication
- authorization
- databases
- transactions
- indexing
- caching
- concurrency
- message queues
- distributed systems
- testing
- logging
- monitoring
- Docker
- CI/CD
- cloud deployment
- security
- scalability
- system design

The system should determine which concepts are relevant to the current project instead of dumping an unnecessary list of technologies on the developer.

The objective is:

> **Don't just generate the code. Help the developer understand the engineering decisions behind the code.**

---

# 4. Software-Company Style Development Workflow

Mantle should simulate a structured software engineering environment.

Instead of:

```text
"Build me an application"
        ↓
AI generates everything
```

Mantle should encourage a workflow closer to how real engineering teams operate:

```text
Requirement
    ↓
Task Breakdown
    ↓
Architecture
    ↓
Technical Decisions
    ↓
Implementation Plan
    ↓
Development
    ↓
Testing
    ↓
Code Review
    ↓
Security Review
    ↓
Documentation
    ↓
Deployment
    ↓
Monitoring
```

Mantle should guide the developer through these stages and identify missing steps, risks, technical debt, and potential scalability problems.

---

# 5. Project-Aware AI Context

Mantle should understand the developer's project instead of treating every conversation as an isolated chat.

It should maintain context about:

- project requirements
- architecture
- source code
- database schema
- APIs
- dependencies
- technical decisions
- documentation
- tasks
- bugs
- previous conversations
- development progress
- testing results

The AI should be able to retrieve the relevant project context when answering a question instead of sending the entire project to every LLM request.

---

# 6. RAG-Based Knowledge System

Mantle should use RAG where appropriate to retrieve relevant information from:

- project source code
- documentation
- technical decisions
- project notes
- database schema
- API documentation
- developer-created knowledge
- selected external documentation

The retrieval system should provide the LLM with only the relevant context required for the current task.

Potential pipeline:

```text
Project Files
     ↓
Parsing / Chunking
     ↓
Embeddings
     ↓
Vector Database
     ↓
Retriever
     ↓
Reranker
     ↓
Relevant Context
     ↓
LLM
```

RAG should not be used blindly. For structured information such as project metadata, tasks, database schemas, and dependency information, use appropriate structured storage and retrieval instead.

---

# 7. AI Agent Orchestration

Mantle can use specialized AI agents for different stages of software development.

For example:

```text
Planner Agent
     ↓
Architecture Agent
     ↓
Coding Agent
     ↓
Testing Agent
     ↓
Security Agent
     ↓
Code Review Agent
     ↓
Documentation Agent
```

A central orchestration layer should determine which agent/tool should handle a task.

**LangGraph** can be used for stateful workflows and agent orchestration where appropriate.

The architecture should avoid creating unnecessary autonomous agents simply for the sake of calling something an "AI agent."

---

# Proposed Technology Stack

## Backend

**Primary language: Python**

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- AsyncIO

FastAPI will provide the core API layer and Python gives Mantle access to the broader AI/LLM ecosystem.

---

## Database

**PostgreSQL**

Use PostgreSQL as the primary system of record for:

- users
- projects
- workspaces
- conversations
- tasks
- model configurations
- usage data
- project metadata
- permissions
- agent execution history
- audit records

Use **pgvector** initially for vector search rather than introducing a separate vector database too early.

This keeps the initial architecture simpler.

---

## LLM Layer

Use a provider-agnostic LLM abstraction.

Recommended:

**LiteLLM**

It can provide a unified interface across multiple model providers.

Potential providers/models can include:

- OpenAI
- Anthropic
- Google
- open-source models
- other compatible providers

Architecture:

```text
Mantle
  ↓
LLM Gateway / Model Router
  ↓
LiteLLM
  ↓
Model Provider
```

This layer is especially important because **model switching is one of Mantle's core problems to solve.**

---

## AI / Agent Layer

Use:

- LangGraph — agent/workflow orchestration
- LangChain — only where its abstractions genuinely simplify implementation
- Pydantic — structured outputs and validation
- tool calling — controlled interaction with project tools

Do **not** make LangChain the foundation of the entire application. Mantle should own its core architecture and use LangChain/LangGraph selectively.

---

## RAG

Recommended initial stack:

- PostgreSQL
- pgvector
- embeddings
- custom retrieval layer
- optional reranker

Potential flow:

```text
Repository / Documents
        ↓
Parser
        ↓
Chunker
        ↓
Embedding Model
        ↓
PostgreSQL + pgvector
        ↓
Retriever
        ↓
Reranker
        ↓
Context Builder
        ↓
LLM
```

---

## Frontend

**React**

Recommended:

- React
- TypeScript
- Vite
- Tailwind CSS
- Monaco Editor

The UI should feel more like a **developer workspace/IDE** than a normal chatbot.

Potential layout:

```text
┌─────────────────────────────────────────────────────┐
│ Mantle AI                           Model: Claude ▼ │
├──────────────┬──────────────────────┬───────────────┤
│              │                      │               │
│ Project      │      Workspace       │   AI Panel    │
│ Explorer     │                      │               │
│              │      Code / Tasks    │   Chat        │
│ Files        │      / Architecture  │   Suggestions │
│ Tasks        │                      │   Context     │
│ Docs         │                      │   Actions     │
│              │                      │               │
├──────────────┴──────────────────────┴───────────────┤
│ Terminal / Logs / Tests / Git / Agent Activity      │
└─────────────────────────────────────────────────────┘
```

---

## Developer Tools

- Git
- GitHub integration
- Docker
- Docker Compose
- Monaco Editor
- terminal integration
- repository indexing
- code search
- test execution
- linting
- formatting
- CI/CD integration

---

# Security

Security must be designed into Mantle from the beginning.

Important areas:

- authentication
- authorization
- workspace isolation
- encrypted API keys/secrets
- secure secret storage
- sandboxed code execution
- command restrictions
- file-system permissions
- prompt injection protection
- tool-call authorization
- audit logs
- rate limiting
- usage limits
- model/provider access controls

**Never allow an LLM to freely execute arbitrary commands on the host machine.**

Code execution should happen inside controlled sandboxed environments.

---

# Scalability

Mantle should be designed so the architecture can evolve from a single-user local development tool into a multi-user platform.

Initial architecture should remain simple:

```text
React
  ↓
FastAPI
  ↓
PostgreSQL
  ↓
pgvector

        ↓
LLM Gateway
        ↓
Multiple LLM Providers
```

As usage grows, components can be separated:

```text
Frontend
   ↓
API Gateway
   ↓
Backend Services
   ├── Project Service
   ├── AI/LLM Service
   ├── RAG Service
   ├── Agent Orchestrator
   ├── Execution Service
   └── Usage/Analytics Service
          ↓
      PostgreSQL
      Redis
      Object Storage
      Queue
```

Do not start with microservices unless there is a real operational reason.

**Start as a modular monolith with clean boundaries. Extract services only when scale or ownership requires it.**

---

# Optional Infrastructure

As the product matures, consider:

- Redis — caching, rate limiting, session/temporary state
- Celery / Dramatiq / Arq — background jobs where required
- S3-compatible object storage — large files/artifacts
- Kafka — only when event volume and architectural requirements justify it
- OpenTelemetry — tracing
- Prometheus/Grafana — metrics and observability
- Docker — consistent development/runtime environments

Kafka should **not** be introduced just because Mantle is an AI platform. PostgreSQL + Redis + a simple job queue is likely enough for the first serious version.

---

# Core Product Principles

Mantle AI should follow these principles:

1. **Context over copy-paste**
2. **Engineering over blind code generation**
3. **Guidance over dependency**
4. **Provider independence**
5. **Project-aware AI**
6. **Secure tool execution**
7. **Observable AI workflows**
8. **Human control over autonomous agents**
9. **Scalable architecture without premature complexity**
10. **Teach developers why, not only what**

---

# End Goal

Mantle AI should become a developer's AI engineering workspace where a developer can:

```text
Create Project
      ↓
Describe Idea
      ↓
Plan Architecture
      ↓
Select / Switch LLM
      ↓
Generate & Understand Code
      ↓
Retrieve Project Context
      ↓
Run Tests
      ↓
Review & Debug
      ↓
Improve Architecture
      ↓
Secure the Application
      ↓
Deploy
      ↓
Monitor
      ↓
Scale
```

The core vision is:

> **Mantle AI helps developers use AI like an experienced software engineering team — without losing context, skipping fundamentals, or blindly relying on generated code.**

The product should make AI-assisted development more structured, transferable between models, educational, reliable, and closer to real-world software engineering practices.