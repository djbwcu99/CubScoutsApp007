const express = require('express');
const router = express.Router();
const bcrypt = require('bcryptjs');
const db = require('../db');

function requireAdmin(req, res, next) {
  if (!req.session || !req.session.isAdmin) {
    return res.status(401).json({ error: 'Unauthorized - admin access required' });
  }
  next();
}

// POST /api/auth/login
router.post('/login', (req, res) => {
  const { password } = req.body;
  if (!password) return res.status(400).json({ error: 'Password required' });

  const setting = db.prepare("SELECT value FROM settings WHERE key = 'admin_password'").get();
  if (!setting) return res.status(500).json({ error: 'No admin password configured' });

  if (bcrypt.compareSync(password, setting.value)) {
    req.session.isAdmin = true;
    res.json({ success: true });
  } else {
    res.status(401).json({ error: 'Incorrect password' });
  }
});

// POST /api/auth/logout
router.post('/logout', (req, res) => {
  req.session.destroy(() => res.json({ success: true }));
});

// GET /api/auth/status
router.get('/status', (req, res) => {
  res.json({ isAdmin: !!(req.session && req.session.isAdmin) });
});

// PUT /api/auth/password
router.put('/password', requireAdmin, (req, res) => {
  const { newPassword } = req.body;
  if (!newPassword || newPassword.length < 6) {
    return res.status(400).json({ error: 'Password must be at least 6 characters' });
  }
  const hash = bcrypt.hashSync(newPassword, 10);
  db.prepare("UPDATE settings SET value = ? WHERE key = 'admin_password'").run(hash);
  res.json({ success: true });
});

module.exports = router;
module.exports.requireAdmin = requireAdmin;
