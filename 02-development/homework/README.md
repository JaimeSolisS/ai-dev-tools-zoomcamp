# Homework 2: Build and Ship an AI-Assisted Full-Stack App

In this homework, we'll build an end-to-end application with AI: a frontend, a backend, and a database.

You will need Python with `uv` for the backend and Node.js for the frontend. You don't need to know any of these technologies for doing this homework.

If some questions are not clear, or you're not sure which answer to select, ask your AI assistant to help.

## Question 1: Pick your project

You can choose one of the four project ideas:

- Expense splitter
- Restaurant waitlist manager
- Mini Kanban board
- Sports-league scoreboard

Pick the one you like most. The workflow is the same for all of them.

Which project did you choose for this homework?

**Answer: Expense splitter**

## Question 2: Spec first

Like in homework 1, we start with a spec.

Open a chat assistant and ask it to help you come up with the specification.

Answer its questions, then ask it to save everything to a markdown file.

```prompt
I want to implement an application for Expense splitter. I will need Python with `uv` for the backend and Node.js for the frontend. Help me set the scope for this project precisely. I want to brainstorm with you and understand how the tool should work. Give me options. Ask me one question at a time and keep your output short. Also help me come up with the name for this application.
```

Also ask it to help you come up with the name for this application.
What's the name you chose?

**Answer: Balancio**

## Question 3: GitHub Repository

Create a new GitHub repository (or a folder in the repository you used for Homework 1), clone it locally. Put the spec there:

- `_docs/specs.md` with the spec
- `.gitignore`
- `README.md`
- `AGENTS.md`

Commit and push. What's the sha1 hash for this commit?

**Answer: 0f40ed0\***

```prompt
read _docs/specs.md and create .gitignore and README.md. Also create AGENTS.md with content similar to this, adapted to what specs.md says:
Commands

- `uv sync` - install dependencies
- `uv run pytest` - the whole suite
- `uv run pytest tests/test_home.py` - one test file

Rules

- Dependencies are added in `pyproject.toml`. Do not add one without
  asking
```

## Question 4: Frontend prototype

Build a frontend prototype with a mocked backend. To make it simpler, use your coding agent directly, not Lovable (but you can experiment with it too).

```text
Implement the frontend for the app described in _docs/specs.md. Put it in frontent/.

Don't implement the backend yet. Centralize all the backend calls
in one place and mock them for now.

Make the UI interactive so I can use the main features from the spec.
```

Iterate until you like the results.

Which command do you use to start the frontend?

**Answer: npm run dev**

## Question 5: Backend

Now let's create the backend. You can first ask your coding assistant to analyze the frontend code and create the specs, and then based on specs create the backend. Or you can create backend directly.

Like in the lessons, we'll first create the backend with a mock database, make sure it integrates well with the frontend, and then replace it with a real database.

Your prompt may look like this:

```text
Based on openapi.yaml, create a FastAPI backend. Use uv for package management.
Use a mock database, we will replace it with a real one later.
Write tests for the endpoints first, then implement them.
```

Which command do you use to start the backend?

**Answer: uv run fastapi dev app/main.py**

## Question 6: Connect frontend and backend

The backend now works (presumably) so let's connect frontent to it. Ask the coding assistant to do it.

You can verify that the connection works manually, but you can also ask your agent to use the browser to check it for you.

```prompt
Connect the frontend with the backend. Use the browser to check that the connection works. After everything works, tell me which URL does the frontend use to talk to the backend?
```

Which URL does the frontend use to talk to the backend?

**Answer: http://localhost:8000/api/v1\***

## Question 7: Database

Now the backend and frontend work fine, you can swap the mock store for a real database.

Keep the app database-agnostic and use SQLAlchemy for that.

Make sure test still pass and add more tests if needed. Ask your agent for recommendations.

```prompt
swap the mock store for a real database. Keep the app database-agnostic and use SQLAlchemy for that. Make sure test still pass and add more tests if needed. After all success, tell me Which command do I use for running tests?
```

Which command do you use for running tests?

**Answer: uv run pytest**

## Submission

Submit your homework here: https://courses.datatalks.club/ai-dev-tools-2026/homework/hw2
