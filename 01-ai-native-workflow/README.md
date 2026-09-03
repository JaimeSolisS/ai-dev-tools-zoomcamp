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

# Bootstrap the first task

Bootstrap the first task
With AGENTS.md and process.md in place, we can start a new session and ask the agent to implement the first task:

```
Implement task 1.
```

For this project, the agent creates the Django app, dependencies, and a passing test.

# Grooming: the product manager agent

We have a backlog of tasks, but they’re not precise enough.

We discussed this problem already: if the task isn’t specific, the agent will fill in the gaps during implementation. We risk spending time and tokens on something we don’t need.

Instead, we should ask the AI assistant to fill these gaps before writing any code. Then we review the specification, correct it, and give it to the coding agent to implement.

This process is called “grooming”: we groom a task to make it more specific. Then an engineer can implement it without asking a single question.

In real teams, product managers usually do this work. Here we’ll create a team of agents, and the first role we’ll define will be a PM.

Create a document

```
_docs/team/
  pm.md
```

Inside, write the description for the product manager agent:

```
You’re a Product Manager

You groom a task before anyone implements it.

- Read the issue as written
- Rewrite it using the template in `_docs/task-template.md`
- Make the acceptance criteria checkable - someone should be able to
  point at the screen and say yes or no
- Think about the edge cases the person who filed it did not consider
- Do not write any code

Definition of done:

- The issue has all four sections filled in
- Every acceptance criterion can be checked by looking at the result
- Everything moved out of scope links to a follow-up issue
- An engineer who has never spoken to you could implement it from the
  issue and the documents it links

If something does not belong in this task, do not silently drop it.
File a follow-up issue and list it under out of scope with a link to
that issue, so it is clear what was moved and where it went.
```

A groomed task has four sections:

Goal - one or two sentences on what should be true afterwards.

Acceptance criteria - checkable statements.

Out of scope - what this change must not do.

Constraints - files it should stay inside, libraries it should or shouldn’t use, prior decisions it has to follow.

We save the issue template as \_docs/task-template.md:

```
## Goal

One or two sentences on what should be true when this is done.

## Acceptance criteria

- [ ] A statement you can check by looking at the result
- [ ] One line per case, including the awkward ones

## Out of scope

- Something that does not belong in this task, moved to #TASK-NUMBER

## Constraints

- Files this should stay inside
- Libraries to use
- Guidelines to follow
```

We’ll need to groom every task, so we’ll add it to process.md:

```
Roles

- PM - grooms a task before anyone implements it, follows _docs/team/pm.md
```

We can now start a new session and ask the agent to groom an issue:

```
Groom issue #4
```

After it finishes, review the result.

We can catch a misunderstanding most cheaply while grooming: the issue is a paragraph, and correcting it costs one sentence. If we catch the same misunderstanding after implementation, we need a rewrite.

# Loop engineering

After grooming one issue, we can ask the agent to groom the rest:

```
Groom all GitHub issues. Process one issue at a time.
```

This will mostly work, but the agent may eventually stop. It might say, “I’ve groomed issues 1, 2, and 3. Do you want me to proceed?”

The answer is almost always “yes”, but the agent has stopped and is waiting for us to say that explicitly. In many cases, I want the agent to continue automatically.

To do it, we can give the agent a goal:

```
/goal groom all issues
```

The /goal command will prompt the agent to continue, so we won’t need to do it manually. Instead, we delegate that responsibility to the harness: the system around an agent, such as Claude Code or Codex. When the agent stops, the harness checks whether the condition has been met. If it hasn’t, the harness resumes the work.

This approach is called “loop engineering”. It’s similar to a while loop: we repeat the work until a condition is met.

With loop engineering, the system runs a coding agent repeatedly instead of having us drive it manually, prompt by prompt.

There are multiple “engineering” levels when we work with coding agents:

Prompt engineering - what we say when we interact with the agent

Context engineering - what the agent knows before it starts and what it can get during the session

Loop engineering - when it stops working

Graph engineering - who does what when there’s more than one agent (we’ll discuss it later)

A loop needs a stop condition: a checkable statement that tells the harness when to stop.

For /goal groom all issues, the stop condition is “all issues are groomed”. After each agent run, the harness checks whether that condition is true and resumes the agent if it isn’t.

The stop condition must be something the model can evaluate. “All issues are groomed”, “all tests pass”, and “no file is over 200 lines” are checkable, but “make the code better” isn’t. If the stop condition isn’t checkable, the agent can stop too early or run forever.

Claude Code and Codex provide the /goal loop by default. If your harness doesn’t provide it, you can implement it yourself using stop hooks.
