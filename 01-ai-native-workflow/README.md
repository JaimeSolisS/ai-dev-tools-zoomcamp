# AI-Native Developer Workflow

Units:

- [AI-Native Developer Workflow](https://aishippingblog.com/p/ai-native-development-specifications)

Homework:

- [Homework 1: AI-Native Developer Workflow](homework.md)

# Walkthrough

## Start in a chat assistant

Instead of giving a prompt directly to the coding assistant, start in a chat application and talk the idea through. Use ChatGPT in dictation mode for this.

Begin with the same vague idea:

```
I want to build a tool for weekly feedback for projects.

Help me set the scope for this project precisely. I want to brainstorm with you
and understand how the tool should work. Give me options.

Ask me one question at a time and keep your output short.
```

This way, we can use AI as our brainstorming partner and find out precisely what we want:

- Who contributes feedback? All team members.
- What format do they use? Start/Stop/Continue.
- Is the feedback anonymous? Names appear by default, but contributors can choose to remain anonymous.
- ...

When we finish, I ask for a file with all the specifications:

```
Save everything to a markdown file that I can download.
```

Download the file and save it as plan.md.

## Bootstrapping a project

Create a project from this specification:

```
mkdir retroloop
cd retroloop

```

Copy the plan.md file in \_docs.

Try to commit as often as possible, after every meaningful decision. With those commits, we can review what the agent changed. If something isn’t working well, we can easily return to the last good state.

## Choose the stack and architecture

During the brainstorming session, we didn’t choose the tech stack.

Ask the coding agent to come up with several options:

```
Read _docs/plan.md. Propose multiple options for the tech stack and
explain each option.

Don't write code yet.
```

It proposes multiple options and explains the tradeoffs of each one. Select one and if not, ask to create architecture.md

## Turn the decisions into a backlog

Now that we’ve settled on the tech stack, we can ask the agent to decompose the specifications into a backlog with tasks:

```
Create a backlog with tasks in _docs/tasks.md.

Each task should be small enough to finish in one session, and
independent enough that I could hand it to someone who has not read
the others.

Use this template for each task:

## <number>. <title>
Goal: <one line>
Description: <two or three sentences on what the task involves>

The first task should be setting up an empty project with a passing test.

Don't write code yet.
```

It created these tasks.md.

Review the tasks and ask the agent to merge tasks that are too small or split tasks that don’t fit into one session. We want to create an MVP - the first version of the app. If something is out of scope for your vision of the MVP, remove it.

When we’re happy with the tasks, move them to a task tracker. I use GitHub issues for that.

```
Create a public GitHub repo for this project.
Move each task from _docs/tasks.md into a GitHub issue.
```

For that to work, we need the gh CLI tool authenticated and the repo connected to the GitHub remote.

From this point on, GitHub issues are the canonical tasks and the only active backlog. We no longer need \_docs/tasks.md.

# Context engineering

The repository has a backlog now. When we start a new session, however, the agent doesn’t know which task we mean. It must figure that out every time.

These details go in AGENTS.md, which coding agents like Codex or OpenCode read when they start a new session.

Claude Code reads CLAUDE.md, while I use multiple coding assistants and want my workflow to be tool-agnostic.

That’s why I also create CLAUDE.md with a single line:

```
@AGENTS.md
```

It tells Claude to read AGENTS.md.

This is called context engineering. With prompt engineering, we control one message in one session. With context engineering, we control what agents know when they start a new session and what information they can find while they work. We include useful facts and working rules they would otherwise have to rediscover.

# AGENTS.md

To make this context available in every new session, create AGENTS.md:

```
Create agents.md with content similar to this
Commands

- `uv sync` - install dependencies
- `uv run pytest` - the whole suite
- `uv run pytest tests/test_home.py` - one test file

Rules

- Dependencies are added in `pyproject.toml`. Do not add one without
  asking

```

# The other documents

In addition to AGENTS.md, I usually have a few other Markdown documents in my projects.

The main one is process.md, which I use to describe how work is organized. It could live inside AGENTS.md, but I keep it separate.

Create \_docs/process.md:

```
- Tasks are GitHub issues, one at a time
- Read the acceptance criteria before starting and before closing
- Commit regularly
```

As I continue working on a project, I may create other documents, such as:

testing-guidelines.md for testing

design-system.md so the UI doesn’t drift every session

api.md, which describes what the API should look like

I keep them together in \_docs/ and link them from AGENTS.md:

```
Documents

- `_docs/process.md` - how work is organized
- Before writing tests, read `_docs/testing-guidelines.md`
- For anything touching the UI, read `_docs/design-system.md`
```

The agent reads AGENTS.md at the start of every session, so it knows where to find the process, testing, and design rules if it needs them.

This way, it will load the design system only for a UI task and the testing guidelines only for a testing task. By loading each document only when it’s relevant, we keep AGENTS.md short while we continue adding written context to the project.

These documents are living documents, and I update them often. If I need to correct an agent during a coding session, I can ask it to modify the documents. Next time, it knows what I need, so I don’t have to correct it again.

You can use a prompt like this:

```
Based on the corrections I made, find the relevant documents and update them.
Commit the current work before changing the documents.
```
