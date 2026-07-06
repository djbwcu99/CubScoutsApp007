const express = require('express');
const router = express.Router();
const db = require('../db');

// GET /api/signups?eventId=X or ?scoutId=X
router.get('/', (req, res) => {
  const { eventId, scoutId } = req.query;
  if (eventId) {
    const signups = db.prepare(`
      SELECT su.*, s.firstName, s.lastName, s.rank, s.den, s.grade, s.parentName, s.parentPhone
      FROM signups su JOIN scouts s ON su.scoutId = s.id
      WHERE su.eventId = ?
      ORDER BY s.rank, s.lastName, s.firstName
    `).all(eventId);
    res.json(signups);
  } else if (scoutId) {
    const signups = db.prepare(`
      SELECT su.*, e.title, e.date, e.time, e.location
      FROM signups su JOIN events e ON su.eventId = e.id
      WHERE su.scoutId = ?
      ORDER BY e.date
    `).all(scoutId);
    res.json(signups);
  } else {
    const signups = db.prepare('SELECT * FROM signups ORDER BY signupDate DESC').all();
    res.json(signups);
  }
});

// POST /api/signups
router.post('/', (req, res) => {
  const { scoutId, eventId, notes } = req.body;
  if (!scoutId || !eventId) {
    return res.status(400).json({ error: 'scoutId and eventId are required' });
  }

  // Check event capacity
  const event = db.prepare('SELECT * FROM events WHERE id = ?').get(eventId);
  if (!event) return res.status(404).json({ error: 'Event not found' });

  if (event.maxSignups) {
    const { count } = db.prepare('SELECT COUNT(*) as count FROM signups WHERE eventId = ?').get(eventId);
    if (count >= event.maxSignups) {
      return res.status(409).json({ error: 'Event is full' });
    }
  }

  try {
    const result = db.prepare(
      'INSERT INTO signups (scoutId, eventId, notes) VALUES (?, ?, ?)'
    ).run(scoutId, eventId, notes || null);
    const signup = db.prepare('SELECT * FROM signups WHERE id = ?').get(result.lastInsertRowid);
    res.status(201).json(signup);
  } catch (err) {
    if (err.message.includes('UNIQUE')) {
      res.status(409).json({ error: 'Scout is already signed up for this event' });
    } else {
      res.status(500).json({ error: err.message });
    }
  }
});

// DELETE /api/signups - by scoutId + eventId
router.delete('/', (req, res) => {
  const { scoutId, eventId } = req.body;
  if (!scoutId || !eventId) {
    return res.status(400).json({ error: 'scoutId and eventId are required' });
  }
  db.prepare('DELETE FROM signups WHERE scoutId = ? AND eventId = ?').run(scoutId, eventId);
  res.json({ success: true });
});

// DELETE /api/signups/:id
router.delete('/:id', (req, res) => {
  db.prepare('DELETE FROM signups WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

module.exports = router;
