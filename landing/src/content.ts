// Every word on the page. Each block names the document it comes from; a claim that no
// document supports does not belong here.

export const REPO = "https://github.com/MohammadAnas-07/MantleAI";
export const blob = (path: string) => `${REPO}/blob/main/${path}`;

export const NAV = [
  { id: "how-it-works", label: "How it works" },
  { id: "features", label: "Features" },
  { id: "privacy", label: "Privacy" },
  { id: "setup", label: "Setup" },
  { id: "status", label: "Status" },
] as const;

// README.md, intro and "Status".
export const HERO = {
  eyebrow: "Open source · MIT licence",
  title: "Switch models without explaining your project again",
  lead: "Mantle keeps project memory, decisions and code search in your own PostgreSQL database, so the next model picks up where the last one stopped.",
  note: "Open source. MIT licence. Runs on your machine, with your own API keys.",
};

// README.md, intro.
export const PROBLEM = {
  title: "A model hits its limit halfway through a task",
  paragraphs: [
    "You copy the chat into another model. Then you spend about 10 minutes explaining the project again: what it is, what you decided, which files matter.",
    "Mantle keeps that context for you. Requirements, decisions, tasks, a rolling summary of the conversation and the indexed code live in a local database. The next model gets them in its first prompt.",
  ],
};

// README.md, "How it works" and "Status"; docs/architecture.md.
export const STEPS = [
  {
    title: "Point Mantle at a project",
    text: "Create a project for a folder of code and add your provider keys. Keys are stored encrypted.",
  },
  {
    title: "It keeps the project's memory",
    text: "Requirements, decisions and tasks are pinned into every prompt. Indexing splits the code into segments for hybrid search and reads a project profile from the files, without a model.",
  },
  {
    title: "A context builder writes each prompt",
    text: "It assembles the system prompt, pinned memory, the profile, the rolling summary, retrieved code and recent messages, within the target model's token budget.",
  },
  {
    title: "Switch models mid-conversation",
    text: "A preview shows what the new model will get. The old model is never called during the switch, so it still works when that model has failed.",
  },
];

// README.md, "Status" (works today, in the API and the web app).
export const FEATURES = [
  {
    title: "Projects, keys and streaming chat",
    detail: "Provider keys are stored encrypted, and a test call checks each key.",
  },
  {
    title: "Model switching mid-conversation",
    detail: "You see a preview first. The model you switch away from is never called.",
  },
  {
    title: "Project memory",
    detail: "Requirements, decisions and tasks are pinned into every prompt, for every model.",
  },
  {
    title: "Indexing and cited answers",
    detail: "Hybrid code search over a local folder, and answers that cite path:lines.",
  },
  {
    title: "A project profile",
    detail: "Languages, dependencies and commands, read from the files without a model.",
  },
  {
    title: "The workflow page",
    detail:
      "Five stages with human approval, a gap finder, and Planner and Reviewer runs whose drafts are saved only when you approve them.",
  },
];

// README.md, "Privacy and security" and "Indexing a project"; docs/security.md.
export const PRIVACY = {
  title: "What leaves your machine, and when",
  rows: [
    {
      what: "Your messages and the prompt Mantle builds",
      to: "The chat model you picked",
      when: "When you send a message",
    },
    {
      what: "Indexed code, split into segments",
      to: "Your embedding model's provider",
      when: "When you index a project",
    },
    {
      what: "Each chat message in an indexed project",
      to: "Your embedding model's provider, as the search query",
      when: "When you send a message",
    },
    {
      what: "The conversation, for the rolling summary",
      to: "The utility model",
      when: "In the background; shown in the usage view, and you can turn it off",
    },
    {
      what: "One tiny test call",
      to: "That key's provider",
      when: "When you test a key",
    },
  ],
  local: [
    "Everything else stays in the local PostgreSQL volume.",
    "Provider keys are stored encrypted and are never returned or logged.",
    "Logs hold ids, counts and error codes, not prompts, replies or file contents.",
    "Mantle never writes to your project folder and runs no shell commands.",
    "The API has no login. It answers only your own computer, and the database listens only on 127.0.0.1. Don't expose either on a network.",
  ],
  warning:
    "Indexing sends your code to your embedding provider (by default Google, gemini-embedding-001). Free tiers may use what you send to train their models. Don't index code you are not allowed to share with that provider.",
  skipped:
    "Mantle skips .env files, keys and certificates, credential files, binaries, files over 1 MB, anything .gitignore matches, and files whose content looks like a secret. This is a safety net, not a guarantee.",
};

// README.md, "Quick start"; docs/setup.md.
export const PREREQUISITES = [
  "Python 3.12 or newer",
  "Docker Desktop, running",
  "Node.js 22 or newer",
  "Git",
];

export const BACKEND_COMMANDS = `docker compose up -d
cd backend
python -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload`;

export const FRONTEND_COMMANDS = `cd frontend
npm install
npm run dev`;

// README.md, "Status", "Limits and known issues".
export const STATUS = {
  works: FEATURES.map((f) => f.title),
  planned: [
    "Teaching notes and the concepts list",
    "A model-written project summary",
    "Sandboxed command execution",
    "Login and accounts",
    "A per-message context view and an audit log endpoint",
  ],
  limits: [
    "No real-use evaluation of v0.1 yet. The 2-week trial hasn't started, and the larger retrieval evaluation stopped at the Gemini daily limit with no result.",
    "Chat and switching have been run for real only on Gemini models. Planner and Reviewer output is one sample, so its quality is not proven.",
    "An agent run on Gemini 3.8 Flash timed out at 120 seconds on the developer's machine.",
    "Index and agent runs live in the server process. A restart stops them.",
    "No login, and the code doesn't yet check that a parent row belongs to the user. Run Mantle only on your own machine.",
    "Some lists stop at a fixed size, for example 500 conversations per project and the newest 200 calls in the activity log.",
    "One Docker volume holds all data, with no automatic backup.",
  ],
};

// mantle-numbers.md, section B "Safe to claim", measured 2026-11-22. Each number keeps its
// condition next to it.
export const NUMBERS = {
  date: "Measured on 2026-11-22.",
  items: [
    {
      value: "883 + 127",
      label: "Backend and frontend tests",
      condition:
        "None need API keys. Backend statement coverage is 97.5% (statements, not branches).",
    },
    {
      value: "14",
      label: "Race tests on real PostgreSQL connections",
      condition: "All passed in 5 of 5 repeated runs, on one laptop.",
    },
    {
      value: "89 ms",
      label: "Median hybrid search time",
      condition:
        "111 ms p95. A 926-segment repository, 30 queries, database time only, on a 2-core i3 laptop with 8 GB.",
    },
    {
      value: "0.3 s",
      label: "To fit 1,000 messages into a 32,000-token budget",
      condition:
        "95.6% of the budget used, no model call. Synthetic messages, local token counter, the same laptop.",
    },
    {
      value: "19",
      label: "Key formats the secret scanner knows",
      condition:
        "Plus 45 sensitive file-name patterns, covered by 135 test cases. A safety net, not a guarantee.",
    },
  ],
};

// README.md, docs/mvp-scope.md, docs/security.md, CLAUDE.md.
export const FAQ = [
  {
    q: "Is Mantle an LLM?",
    a: "No. Mantle is a workspace. It calls the model providers you choose, with your own API keys.",
  },
  {
    q: "Which providers does it support?",
    a: "You can add keys for OpenAI, Anthropic, Google and Voyage. Chat and model switching have been run for real only on Gemini models so far. A free Google AI Studio key is enough for chat and for indexing.",
  },
  {
    q: "Where does my code go?",
    a: "The indexed code is stored in your local PostgreSQL database. Indexing sends its segments to your embedding provider, and retrieved segments go to the chat model inside your prompts. Mantle never writes to your project folder.",
  },
  {
    q: "Does it need the internet?",
    a: "Only to reach the providers you use, when you send a message, index a project or test a key, plus the background summary if it is on. The database and the app run on your machine.",
  },
  {
    q: "Why is there no login?",
    a: "Version 0.1 is for one developer on their own computer. The API answers only that computer and the database listens only on 127.0.0.1. Login and accounts are planned.",
  },
  {
    q: "How can I contribute?",
    a: "Read CLAUDE.md and docs/rules.md first. Work on one roadmap item per branch, named type/short-topic, and open a pull request. Tests need no API keys and no network.",
  },
];

// README.md, "Status" and the licence line.
export const FOOTER = {
  statement: "Your project's memory, in your own database.",
  columns: [
    {
      title: "Project",
      links: [
        { label: "GitHub", href: REPO },
        { label: "README", href: blob("README.md") },
        { label: "Docs", href: `${REPO}/tree/main/docs` },
        { label: "Roadmap", href: blob("docs/roadmap.md") },
      ],
    },
    {
      title: "Setup",
      links: [
        { label: "Quick start", href: "#setup" },
        { label: "Troubleshooting", href: `${blob("docs/setup.md")}#common-errors` },
      ],
    },
    {
      title: "Legal",
      links: [
        { label: "MIT licence", href: blob("LICENSE") },
        { label: "Security notes", href: blob("docs/security.md") },
      ],
    },
  ],
  builder: "One developer builds Mantle. Version 0.1 is not finished.",
  licence: "Released under the MIT licence.",
};
