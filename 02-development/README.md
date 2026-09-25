# Build and Ship a Full-Stack App with AI Coding Assistants

## Overview

From there, we start building:

1. Generate a frontend that uses mocked backend calls.

2. Establish backend-frontend contract by creating OpenAPI specifications from the frontend service layer.

3. Implement the FastAPI backend, connect it to the frontend, and test the application.

4. Add persistence with SQLite and SQLAlchemy.

At each stage we get something concrete that we can test:

- First we define the specification and make sure it reflects what we want to build.

- After that, we use the specs to create a frontend prototype that we can interact with. We mock backend calls so we can test the idea.

- Then we connect the frontend to the backend. We start with an in-memory store to make sure the frontend-backend connection works.

- Finally, we add a database so the application keeps its state after a restart.

At the end, we have a working local application that is ready for deployment.

<p align="center">
  <img width="100%" src="img/overview.png" alt="AI Dev Tools Zoomcamp Cover Image">
  <p align="center">The interfaces stay stable while temporary components are replaced one at a time</p>
</p>

# Start with a specification

Before building the frontend, we need to describe the application precisely. If we don’t do it, we will get something that works but we don’t need.

For our application, we need to specify:

- who creates an interview session

- how a candidate joins it

- which components they can place on the canvas

- how both people see changes in real time

This is called “Specification-Driven Development”. For creating the specification, I always use ChatGPT in dictation mode. Give the assistant as much information as possible at this stage.

The result is [here](app/_docs/spec.md)

## Frontend First

Now we have the specification, but it’s only text. There are multiple options of what you can do next:

- Focus on the database layer, define the entities, and work all the way up through backend to frontend
- Alternatively, you can start with specifying OpenAPI and define how backend and frontend interact and build both independently from there
- Or you can focus on the frontend first and then build the rest

All these approaches make sense and have their pros and cons.

For simple projects that you’re building alone, I recommend starting with frontend. You can quickly judge if you’re moving in the right direction, and if it solves your problem or not.

Treat it as a way to test your idea and your specification, and do it before you build the rest of the application.

For this step I like using Lovable, which generates a React app from one prompt. Claude Design, Replit, v0, and Bolt are similar tools that you can use instead.

Alternatively, you can start with coding assistants directly and ask them to create a React app (or whatever technology you want).

I use Lovable because it creates really nice designs. Also, I’m not a frontend engineer and I don’t know much about the frontend world. Lovable makes technology choices for me that I know will make sense, while a coding agent can select something randomly.

Now open any tool of your choice and give it this prompt:

```
Create a system design interview application.

[Paste the ChatGPT-generated specification here.]

Centralize every backend call in one services layer, and create a mock
implementation of it so the whole app runs without a real backend.

Add tests.
```

This part is quite important:

> Centralize every backend call in one services layer, and create a mock implementation of it so the whole app runs without a real backend.

Without it, the agent can do something arbitrary, but here we explicitly say that we want a mock service. Later, it will become the single point of integration of our frontend with backend. And because we mock it, it will work from the beginning.

<p align="center">
  <img width="80%" src="img/frontend.png" alt="AI Dev Tools Zoomcamp Cover Image">
  <p align="center">The frontend is real and interactive; only its backend service is mocked</p>
</p>

Lovable creates a React app in TypeScript. We can interact with it in the Lovable interface.

Next, save it to GitHub. If you use Lovable:

- Select the plus icon in the bottom-left corner
- Connect your GitHub account.
- Lovable creates a private repository. I usually change it to public.
