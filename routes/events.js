const express = require('express');
const router = express.Router();
const db = require('../db');
const { requireAdmin } = require('./auth');

// GET /api/events
router.get('/', (req, res) => {
  const events = db.prepare('SELECT * FROM events ORDER BY date, time').all();
  // Attach signup counts
  const withCounts = events.map(e => {
    const { count } = db.prepare('SELECT COUNT(*) as count FROM signups WHERE eventId = ?').get(e.id);
    return { ...e, signupCount: count };
  });
  res.json(withCounts);
});

// GET /api/events/:id
router.get('/:id', (req, res) => {
  const event = db.prepare('SELECT * FROM events WHERE id = ?').get(req.params.id);
  if (!event) return res.status(404).json({ error: 'Event not found' });

  const signups = db.prepare(`
    SELECT s.id as scoutId, s.firstName, s.lastName, s.rank, s.den, s.grade,
           s.parentName, s.parentEmail, s.parentPhone,
           su.id as signupId, su.signupDate, su.notes as signupNotes
    FROM signups su
    JOIN scouts s ON su.scoutId = s.id
    WHERE su.eventId = ?
    ORDER BY s.rank, s.lastName, s.firstName
  `).all(req.params.id);

  res.json({ ...event, signups, signupCount: signups.length });
});

// POST /api/events
router.post('/', requireAdmin, (req, res) => {
  const { title, date, time, location, description, maxSignups } = req.body;
  if (!title || !date) {
    return res.status(400).json({ error: 'title and date are required' });
  }
  const result = db.prepare(
    'INSERT INTO events (title, date, time, location, description, maxSignups) VALUES (?, ?, ?, ?, ?, ?)'
  ).run(title, date, time || null, location || null, description || null, maxSignups || null);

  const event = db.prepare('SELECT * FROM events WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json({ ...event, signupCount: 0 });
});

// PUT /api/events/:id
router.put('/:id', requireAdmin, (req, res) => {
  const { title, date, time, location, description, maxSignups } = req.body;
  const existing = db.prepare('SELECT id FROM events WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: 'Event not found' });

  db.prepare(
    'UPDATE events SET title=?, date=?, time=?, location=?, description=?, maxSignups=? WHERE id=?'
  ).run(title, date, time || null, location || null, description || null, maxSignups || null, req.params.id);

  const event = db.prepare('SELECT * FROM events WHERE id = ?').get(req.params.id);
  const { count } = db.prepare('SELECT COUNT(*) as count FROM signups WHERE eventId = ?').get(req.params.id);
  res.json({ ...event, signupCount: count });
});

// DELETE /api/events/:id
router.delete('/:id', requireAdmin, (req, res) => {
  const existing = db.prepare('SELECT id FROM events WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: 'Event not found' });
  db.prepare('DELETE FROM events WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

module.exports = router;
