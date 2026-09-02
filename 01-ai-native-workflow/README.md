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
