const express = require('express');
const router = express.Router();
const db = require('../db');
const { requireAdmin } = require('./auth');

// GET /api/scouts
router.get('/', (req, res) => {
  const scouts = db.prepare('SELECT * FROM scouts ORDER BY rank, lastName, firstName').all();
  res.json(scouts);
});

// GET /api/scouts/:id
router.get('/:id', (req, res) => {
  const scout = db.prepare('SELECT * FROM scouts WHERE id = ?').get(req.params.id);
  if (!scout) return res.status(404).json({ error: 'Scout not found' });
  res.json(scout);
});

// POST /api/scouts
router.post('/', requireAdmin, (req, res) => {
  const { firstName, lastName, rank, den, grade, dateJoined, parentName, parentEmail, parentPhone, notes } = req.body;
  if (!firstName || !lastName || !rank) {
    return res.status(400).json({ error: 'firstName, lastName, and rank are required' });
  }
  const result = db.prepare(
    'INSERT INTO scouts (firstName, lastName, rank, den, grade, dateJoined, parentName, parentEmail, parentPhone, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
  ).run(firstName, lastName, rank, den || null, grade || null, dateJoined || null, parentName || null, parentEmail || null, parentPhone || null, notes || null);
  const scout = db.prepare('SELECT * FROM scouts WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json(scout);
});

// PUT /api/scouts/:id
router.put('/:id', requireAdmin, (req, res) => {
  const { firstName, lastName, rank, den, grade, dateJoined, parentName, parentEmail, parentPhone, notes } = req.body;
  const existing = db.prepare('SELECT id FROM scouts WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: 'Scout not found' });

  db.prepare(
    'UPDATE scouts SET firstName=?, lastName=?, rank=?, den=?, grade=?, dateJoined=?, parentName=?, parentEmail=?, parentPhone=?, notes=? WHERE id=?'
  ).run(firstName, lastName, rank, den || null, grade || null, dateJoined || null, parentName || null, parentEmail || null, parentPhone || null, notes || null, req.params.id);

  const scout = db.prepare('SELECT * FROM scouts WHERE id = ?').get(req.params.id);
  res.json(scout);
});

// DELETE /api/scouts/:id
router.delete('/:id', requireAdmin, (req, res) => {
  const existing = db.prepare('SELECT id FROM scouts WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: 'Scout not found' });
  db.prepare('DELETE FROM scouts WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

module.exports = router;
