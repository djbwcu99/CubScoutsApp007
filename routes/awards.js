const express = require('express');
const router = express.Router();
const db = require('../db');
const { requireAdmin } = require('./auth');

const DEFAULT_AWARDS = {
  Lion: [
    { name: 'Lion Badge', type: 'rank_badge' },
    { name: 'Animal Kingdom Adventure', type: 'required_adventure' },
    { name: 'Big Cats', type: 'elective_adventure' },
    { name: 'Curiosity, Intrigue, and Magical Mysteries', type: 'elective_adventure' },
    { name: 'Gizmos and Gadgets', type: 'elective_adventure' },
    { name: 'Happy Hunting', type: 'elective_adventure' },
    { name: 'Let It Grow', type: 'elective_adventure' },
    { name: 'Make It Move', type: 'elective_adventure' },
    { name: 'My Family\'s Duty to God', type: 'elective_adventure' },
    { name: 'Rumble in the Jungle', type: 'elective_adventure' },
  ],
  Tiger: [
    { name: 'Tiger Badge', type: 'rank_badge' },
    { name: 'Tiger Bites', type: 'required_adventure' },
    { name: 'Built by Baden-Powell', type: 'elective_adventure' },
    { name: 'Curiosity, Intrigue, and Magical Mysteries', type: 'elective_adventure' },
    { name: 'Earn Your Stripes', type: 'elective_adventure' },
    { name: 'Gizmos and Gadgets', type: 'elective_adventure' },
    { name: 'Movin\' On', type: 'elective_adventure' },
    { name: 'My Family\'s Duty to God', type: 'elective_adventure' },
    { name: 'Sky is the Limit', type: 'elective_adventure' },
    { name: 'Tiger-iffic', type: 'elective_adventure' },
    { name: 'Tigers in the Wild', type: 'elective_adventure' },
  ],
  Wolf: [
    { name: 'Wolf Badge', type: 'rank_badge' },
    { name: 'Call of the Wild', type: 'required_adventure' },
    { name: 'Duty to God Footsteps', type: 'required_adventure' },
    { name: 'Howling at the Moon', type: 'required_adventure' },
    { name: 'Paws on the Path', type: 'required_adventure' },
    { name: 'Running with the Pack', type: 'required_adventure' },
    { name: 'Adventures in Coins', type: 'elective_adventure' },
    { name: 'Air of the Wolf', type: 'elective_adventure' },
    { name: 'Code of the Wolf', type: 'elective_adventure' },
    { name: 'Cubs who Care', type: 'elective_adventure' },
    { name: 'Digging in the Past', type: 'elective_adventure' },
    { name: 'Finding Your Way', type: 'elective_adventure' },
    { name: 'Paws of Skill', type: 'elective_adventure' },
    { name: 'Spirit of the Water', type: 'elective_adventure' },
  ],
  Bear: [
    { name: 'Bear Badge', type: 'rank_badge' },
    { name: 'Bear Claws', type: 'required_adventure' },
    { name: 'Bear Necessities', type: 'required_adventure' },
    { name: 'Fellowship and Duty to God', type: 'required_adventure' },
    { name: 'Fur, Feathers, and Ferns', type: 'required_adventure' },
    { name: 'Baloo the Builder', type: 'elective_adventure' },
    { name: 'Beat of the Drum', type: 'elective_adventure' },
    { name: 'A Bear Goes Fishing', type: 'elective_adventure' },
    { name: 'Forensics', type: 'elective_adventure' },
    { name: 'Grin and Bear It', type: 'elective_adventure' },
    { name: 'Make It Move', type: 'elective_adventure' },
    { name: 'Robotics', type: 'elective_adventure' },
    { name: 'Super Science', type: 'elective_adventure' },
  ],
  Webelos: [
    { name: 'Webelos Badge', type: 'rank_badge' },
    { name: 'Duty to God and You', type: 'required_adventure' },
    { name: 'First Responder', type: 'required_adventure' },
    { name: 'Stronger, Faster, Higher', type: 'required_adventure' },
    { name: 'Into the Wild', type: 'required_adventure' },
    { name: 'Into the Woods', type: 'required_adventure' },
    { name: 'Build My Own Hero', type: 'elective_adventure' },
    { name: 'Earth Rocks', type: 'elective_adventure' },
    { name: 'Engineer', type: 'elective_adventure' },
    { name: 'Fix It', type: 'elective_adventure' },
    { name: 'Game Design', type: 'elective_adventure' },
    { name: 'Maestro!', type: 'elective_adventure' },
    { name: 'Webelos Walkabout', type: 'elective_adventure' },
  ],
  AOL: [
    { name: 'Arrow of Light Badge', type: 'rank_badge' },
    { name: 'Building a Better World', type: 'required_adventure' },
    { name: 'Duty to God and Country', type: 'required_adventure' },
    { name: 'Scouting Adventure', type: 'required_adventure' },
    { name: 'Camper', type: 'elective_adventure' },
    { name: 'Cyclist', type: 'elective_adventure' },
    { name: 'First Aid', type: 'elective_adventure' },
    { name: 'Fishing', type: 'elective_adventure' },
    { name: 'Floater', type: 'elective_adventure' },
    { name: 'Into the Wild', type: 'elective_adventure' },
    { name: 'Into the Woods', type: 'elective_adventure' },
    { name: 'Outdoor Adventurer', type: 'elective_adventure' },
    { name: 'Paddle Craft', type: 'elective_adventure' },
  ],
};

// GET /api/awards?scoutId=X
router.get('/', (req, res) => {
  const { scoutId } = req.query;
  if (scoutId) {
    const awards = db.prepare('SELECT * FROM awards WHERE scoutId = ? ORDER BY type, name').all(scoutId);
    res.json(awards);
  } else {
    const awards = db.prepare('SELECT * FROM awards ORDER BY scoutId, type, name').all();
    res.json(awards);
  }
});

// GET /api/awards/defaults/:rank
router.get('/defaults/:rank', (req, res) => {
  const awards = DEFAULT_AWARDS[req.params.rank] || [];
  res.json(awards);
});

// POST /api/awards
router.post('/', requireAdmin, (req, res) => {
  const { scoutId, name, type, status, progress, dateEarned, notes } = req.body;
  if (!scoutId || !name || !type) {
    return res.status(400).json({ error: 'scoutId, name, and type are required' });
  }
  const result = db.prepare(
    'INSERT INTO awards (scoutId, name, type, status, progress, dateEarned, notes) VALUES (?, ?, ?, ?, ?, ?, ?)'
  ).run(scoutId, name, type, status || 'not_started', progress || 0, dateEarned || null, notes || null);
  const award = db.prepare('SELECT * FROM awards WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json(award);
});

// PUT /api/awards/:id
router.put('/:id', requireAdmin, (req, res) => {
  const { name, type, status, progress, dateEarned, notes } = req.body;
  const existing = db.prepare('SELECT id FROM awards WHERE id = ?').get(req.params.id);
  if (!existing) return res.status(404).json({ error: 'Award not found' });

  db.prepare(
    'UPDATE awards SET name=?, type=?, status=?, progress=?, dateEarned=?, notes=? WHERE id=?'
  ).run(name, type, status, progress, dateEarned || null, notes || null, req.params.id);

  const award = db.prepare('SELECT * FROM awards WHERE id = ?').get(req.params.id);
  res.json(award);
});

// DELETE /api/awards/:id
router.delete('/:id', requireAdmin, (req, res) => {
  db.prepare('DELETE FROM awards WHERE id = ?').run(req.params.id);
  res.json({ success: true });
});

// POST /api/awards/bulk - load default awards for a scout's rank
router.post('/bulk', requireAdmin, (req, res) => {
  const { scoutId, rank } = req.body;
  const scout = db.prepare('SELECT * FROM scouts WHERE id = ?').get(scoutId);
  if (!scout) return res.status(404).json({ error: 'Scout not found' });

  const rankToUse = rank || scout.rank;
  const defaults = DEFAULT_AWARDS[rankToUse] || [];

  const insert = db.prepare(
    'INSERT OR IGNORE INTO awards (scoutId, name, type, status, progress) VALUES (?, ?, ?, ?, ?)'
  );
  const insertMany = db.transaction((items) => {
    for (const item of items) {
      insert.run(scoutId, item.name, item.type, 'not_started', 0);
    }
  });
  insertMany(defaults);

  const awards = db.prepare('SELECT * FROM awards WHERE scoutId = ? ORDER BY type, name').all(scoutId);
  res.json(awards);
});

module.exports = router;
