import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { liveElements } from '../../canvas/model';
import { createMockBackend } from '../../services/mock/mockBackend';
import { renderApp } from '../../test/render';
import { createWorld, signIn } from '../../test/world';

describe('interviewer sign-in and dashboard', () => {
  it('redirects to login, signs in with the magic link and shows the dashboard', async () => {
    const user = userEvent.setup();
    const backend = createMockBackend();
    renderApp(backend, '/');

    await user.type(await screen.findByLabelText('Work email'), 'ada@example.com');
    await user.click(screen.getByRole('button', { name: /email me a sign-in link/i }));
    await user.click(await screen.findByRole('button', { name: 'Open sign-in link' }));

    expect(await screen.findByRole('heading', { name: 'Interviews' })).toBeInTheDocument();
    const table = await screen.findByRole('table');
    expect(within(table).getByRole('link', { name: 'Example: Design a URL shortener' })).toBeInTheDocument();
    expect(within(table).getByText('Ended')).toBeInTheDocument();
    expect(screen.getByText('Ada')).toBeInTheDocument();
  });

  it('shows validation errors from the backend', async () => {
    const user = userEvent.setup();
    renderApp(createMockBackend(), '/login');
    const input = await screen.findByLabelText('Work email');
    // Bypass native email validation to exercise the backend check.
    input.setAttribute('type', 'text');
    await user.type(input, 'not-an-email');
    await user.click(screen.getByRole('button', { name: /sign-in link/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Enter a valid email address.');
  });

  it('creates a new interview and opens its room', async () => {
    const user = userEvent.setup();
    const backend = createMockBackend({ seedExamples: false });
    await signIn(backend);
    renderApp(backend, '/sessions/new');

    await user.type(await screen.findByLabelText('Title'), 'Design Twitter');
    await user.type(screen.getByLabelText(/Problem statement/), 'Home timeline for 200M users');
    await user.click(screen.getByRole('button', { name: 'Create interview' }));

    expect(await screen.findByRole('heading', { level: 1, name: 'Design Twitter' })).toBeInTheDocument();
    expect(screen.getByText('Home timeline for 200M users')).toBeInTheDocument();
    expect(screen.getByText('Draft')).toBeInTheDocument();
    const sessions = await backend.sessions.list();
    expect(sessions.map((s) => s.title)).toEqual(['Design Twitter']);
  });

  it('duplicates and archives sessions from the dashboard', async () => {
    const user = userEvent.setup();
    const backend = createMockBackend({ seedExamples: false });
    await signIn(backend);
    await backend.sessions.create({ title: 'Rate limiter' });
    renderApp(backend, '/');

    await user.click(await screen.findByRole('button', { name: 'Archive Rate limiter' }));
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Archive' }));
    await waitFor(() => expect(screen.queryByRole('link', { name: 'Rate limiter' })).not.toBeInTheDocument());
    await user.click(screen.getByLabelText(/Show archived/));
    expect(await screen.findByText('Archived')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Duplicate Rate limiter' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Rate limiter (copy)' })).toBeInTheDocument();
  });
});

describe('candidate lobby', () => {
  it('explains invalid links', async () => {
    renderApp(createMockBackend(), '/join/bogus-token');
    expect(await screen.findByRole('heading', { name: 'Can’t join this interview' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('not valid');
  });

  it('joins with a display name after accepting the notice', async () => {
    const user = userEvent.setup();
    const world = createWorld();
    const owner = world.client();
    await signIn(owner);
    const session = await owner.sessions.create({ title: 'Design Uber', prompt: 'Match riders with drivers' });
    await owner.sessions.start(session.id);
    const { token } = await owner.sessions.createGuestLink(session.id);

    const candidate = world.client();
    renderApp(candidate, `/join/${token}`);
    expect(await screen.findByRole('heading', { name: 'Design Uber' })).toBeInTheDocument();
    expect(screen.getByText('You are joining as the candidate.')).toBeInTheDocument();
    expect(screen.getByText(/Canvas activity is saved automatically/)).toBeInTheDocument();

    await user.type(screen.getByLabelText('Your name'), 'Linus');
    await user.click(screen.getByRole('button', { name: 'Join interview' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('accept the notice');

    await user.click(screen.getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: 'Join interview' }));

    expect(await screen.findByText('Match riders with drivers')).toBeInTheDocument();
    // Candidates don't get host controls.
    expect(screen.queryByRole('button', { name: /End interview/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Share/ })).not.toBeInTheDocument();
    expect((await owner.sessions.listParticipants(session.id)).map((p) => p.displayName)).toContain('Linus');
  });
});

describe('interview room', () => {
  async function ownerRoom(opts: { start?: boolean } = {}) {
    const world = createWorld();
    const owner = world.client();
    await signIn(owner);
    const session = await owner.sessions.create({ title: 'Design Dropbox', prompt: 'Sync files across devices' });
    if (opts.start) await owner.sessions.start(session.id);
    const user = userEvent.setup();
    renderApp(owner, `/sessions/${session.id}`);
    await screen.findByTestId('canvas');
    await waitFor(() => expect(screen.getByTestId('connection-status')).toHaveTextContent('All changes saved'));
    return { world, owner, session, user };
  }

  it('adds components from the library and shows their properties', async () => {
    const { owner, session, user } = await ownerRoom();
    await user.click(screen.getByRole('button', { name: 'Component library' }));
    await user.click(screen.getByRole('button', { name: 'Add Load balancer' }));

    const canvas = screen.getByTestId('canvas');
    expect(within(canvas).getAllByLabelText('Load balancer: Load balancer').length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: 'Properties' })).toBeInTheDocument();
    const label = screen.getByLabelText('Label');
    await user.clear(label);
    await user.type(label, 'Edge LB');
    await user.tab();

    await waitFor(async () => {
      const room = await owner.canvas.openRoom(session.id);
      const [el] = liveElements(room.canvas);
      expect(el).toMatchObject({ kind: 'shape', componentType: 'load-balancer', label: 'Edge LB' });
    });
  });

  it('supports keyboard delete, undo and redo', async () => {
    const { user } = await ownerRoom();
    await user.keyboard('l');
    await user.click(screen.getByRole('button', { name: 'Add Cache' }));
    const canvas = screen.getByTestId('canvas');
    expect(within(canvas).getAllByLabelText(/^Cache/).length).toBeGreaterThan(0);
    // Focus leaves the library button so shortcuts apply to the canvas.
    canvas.focus();
    await user.keyboard('{Delete}');
    expect(within(canvas).queryAllByLabelText(/^Cache/)).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    expect(within(canvas).getAllByLabelText(/^Cache/).length).toBeGreaterThan(0);
    await user.click(screen.getByRole('button', { name: 'Redo' }));
    expect(within(canvas).queryAllByLabelText(/^Cache/)).toHaveLength(0);
  });

  it('switches tools with keyboard shortcuts', async () => {
    const { user } = await ownerRoom();
    screen.getByTestId('canvas').focus();
    await user.keyboard('p');
    expect(screen.getByRole('button', { name: 'Pen' })).toHaveAttribute('aria-pressed', 'true');
    await user.keyboard('c');
    expect(screen.getByRole('button', { name: 'Connector' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('group', { name: 'Connector options' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Select' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('starts, locks candidate editing and ends the interview', async () => {
    const { owner, session, user } = await ownerRoom();
    await user.click(screen.getByRole('button', { name: 'Start interview' }));
    expect(await screen.findByText('Live')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Candidate can edit' }));
    expect(await screen.findByRole('button', { name: 'Candidate locked' })).toBeInTheDocument();
    expect((await owner.sessions.get(session.id)).candidateEditingEnabled).toBe(false);

    await user.click(screen.getByRole('button', { name: 'End interview' }));
    const dialog = screen.getByRole('dialog', { name: 'End the interview?' });
    await user.click(within(dialog).getByRole('button', { name: 'End interview' }));
    expect(await screen.findByText(/This interview has ended/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reopen' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pen' })).toBeDisabled();
    expect((await owner.sessions.get(session.id)).state).toBe('ended');
  });

  it('creates a shareable candidate link', async () => {
    const { owner, session, user } = await ownerRoom();
    await user.click(screen.getByRole('button', { name: 'Share' }));
    await user.click(screen.getByRole('button', { name: 'Create candidate link' }));
    const input = (await screen.findByLabelText('Invitation link')) as HTMLInputElement;
    expect(input.value).toMatch(/\/join\/[\w-]{22,}$/);
    const links = await owner.sessions.listGuestLinks(session.id);
    expect(links).toHaveLength(1);
    expect(links[0].roleGranted).toBe('candidate');
  });

  it('shows the candidate a locked banner and live participant changes', async () => {
    const world = createWorld();
    const owner = world.client();
    await signIn(owner);
    const session = await owner.sessions.create({ title: 'Design Slack' });
    await owner.sessions.start(session.id);
    const { token } = await owner.sessions.createGuestLink(session.id);
    const candidate = world.client();
    await candidate.join.join(token, 'Linus');

    renderApp(candidate, `/sessions/${session.id}`);
    await screen.findByTestId('canvas');
    await waitFor(() => expect(screen.getByTestId('connection-status')).toHaveTextContent('All changes saved'));
    expect(screen.getByRole('button', { name: 'Pen' })).toBeEnabled();

    await owner.sessions.update(session.id, { candidateEditingEnabled: false });
    expect(await screen.findByText('The interviewer has paused candidate editing.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Pen' })).toBeDisabled();
  });

  it('tells people without access to use their invitation link', async () => {
    const world = createWorld();
    const owner = world.client();
    await signIn(owner);
    const session = await owner.sessions.create({ title: 'Private' });
    renderApp(world.client(), `/sessions/${session.id}`);
    expect(await screen.findByRole('heading', { name: 'Join with your invitation link' })).toBeInTheDocument();
  });
});
