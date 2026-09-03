# Homework 1: AI-Native Developer Workflow

In this homework, we'll build an application with AI — but instead of us handing you a finished spec, you'll turn a vague idea into one yourself, then implement it in Django.

You can use any coding agent you want: Claude Code, Codex CLI, Gemini CLI, Cursor, Aider, GitHub Copilot, etc. Pick **one** and stick with it for the whole homework — with chat-based tools you'd need to copy code back and forth, so we recommend an agent that can edit files and run commands directly in your project.

You will only need Python to get started (we also recommend that you use `uv`). You don't need to know Python or Django for doing this homework.

## Project Idea

We will work on a project with a very vague idea:

> A tool for managing shared household chores

We don't specify anything else, and most of you will finish with different projects.

In this homework, we want to turn this vague description into a clear specification.

## Question 1: Select your coding agent

You can use any coding agent you want. Which one did you choose?

**Answer: Claude Code**

## Question 2: Turn the idea into a spec

Open a chat assistant and brainstorm with a prompt like:

```text
I want to build a tool for managing shared household chores.

Help me set the scope for this project precisely. I want to brainstorm with you
and understand how the tool should work. Give me options.

Ask me one question at a time and keep your output short.
```

Answer its questions, then ask it to save everything to a markdown file.

What are the 2-4 features your spec settled on?

**Answer:**
The spec settled on these 4 core MVP features:

1. Shared chore calendar

- Month and week views
- Chores shown by due date
- Shows title, assignee, and status
- Overdue chores remain visible

2. Chore management

- Create one-time chores with title, description, due date, assignee(s), and category
- Statuses: Pending, In progress, Done
- Admins can edit chores before completion
- Members can create chores only for themselves

3. Household member management

- Admin creates member accounts with username + password + display name
- Simple Admin / Member roles
- Admin can remove members and manage assignments

4. Basic completion history

- Everyone can view a chronological history
- Shows completed chores and completion date
- Reopened chores are removed from completion history\*\*

## GitHub Repository

Create an empty GitHub repository, clone it locally. Create two files there:

- `.gitignore`
- `README.md`
- `_docs/plan.md` with the plan

Commit and push.

## Question 3: Django project

For this project we'll use Django.

Ask your agent to install Django and create a project and an app for it. At some point, you will need to include the app you created in the project.

What's the file you need to edit for that?

- `settings.py`
- `manage.py`
- `urls.py`
- `wsgi.py`

For this and next questions you can ask your coding assistant to select the correct option.

Prompts:

```
For this project we'll use Django. Install Django and create a project and an app for it.
```

```
 At some point, I will to include the app created in the project. What is the file I need to edit for that?
  - settings.py
  - manage.py
  - urls.py
  - wsgi.py
```

**Answer: settings.py — you add the app to the INSTALLED_APPS list (already done for chores in config/settings.py).**

## Question 4: Backlog

Then give your agent the `plan.md` and ask it to propose a small backlog of tasks for building this in Django. Write the result to `backlog.md`.

What's task 1 in the backlog your agent came up with?

```prompt
Read _docs/plan.md and to propose a small backlog of tasks for building this in Django. Write the result to `backlog.md`
```

**Answer: ## 1. Foundations **

- [ ] **Data models**: `Household`, `User` (extend `AbstractUser` with `display_name`, `role`, `household` FK), `Category` (seeded, `is_system`), `Chore`, `ChoreAssignee` (join table), `CompletionHistory`. Design `User`/`Household` as a FK now (not M2M) so multi-household support can be added later without a schema rewrite.
- [ ] **Custom user model wiring**: set `AUTH_USER_MODEL`, register in admin, initial migration. Must be done before any other migration touches `User`.
- [ ] **Seed data**: management command or migration to create the fixed category list (Cleaning, Kitchen, Laundry, Bathroom, Bedroom, Shopping, Trash, Pet Care, Other).

## Question 5: First version

Implement the first few tasks. Just open your agent and say:

```
Implement task #1 from backlog.md
```

Run the server. Which command do you use to start the Django development server?

- `uv run python manage.py runserver`
- `uv run django-admin startserver`
- `python manage.py start`
- `uv run python app.py runserver`

**Answer: uv run python manage.py runserver**

## Question 6: Tests

After implementing a few items from the backlog, let's make sure the code is covered with tests.

- Tell the agent we want to cover the code with tests
- Ask it which scenarios we should cover
- Make sure they make sense
- Let it implement them and run them

What's the command you use for running tests in the terminal?

- `pytest`
- `python manage.py test`
- `python -m django run_tests`
- `django-admin test`

```prompt
I want to cover the code with tests. which scenarios we should cover? Make sure they make sense. Implement them and run them.
```

## Submission

Submit your homework here: https://courses.datatalks.club/ai-dev-tools-2026/homework/hw1

Use the link to repository you created in the homework submission form.
