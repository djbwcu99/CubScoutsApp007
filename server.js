const express = require('express');
const path = require('path');
const session = require('express-session');

const app = express();
const PORT = process.env.PORT || 3000;

// ─── Middleware ──────────────────────────────────────────────
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));
app.use(session({
  secret: process.env.SESSION_SECRET || 'cub-scouts-pack-manager-secret-2024',
  resave: false,
  saveUninitialized: false,
  cookie: { secure: false, maxAge: 24 * 60 * 60 * 1000 } // 24 hours
}));

// ─── API Routes ──────────────────────────────────────────────
app.use('/api/auth',    require('./routes/auth'));
app.use('/api/scouts',  require('./routes/scouts'));
app.use('/api/awards',  require('./routes/awards'));
app.use('/api/events',  require('./routes/events'));
app.use('/api/signups', require('./routes/signups'));
app.use('/api/exports', require('./routes/exports'));

// ─── SPA Fallback ────────────────────────────────────────────
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ─── Start ───────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log('');
  console.log('  ⚜️  ================================');
  console.log('      CUB SCOUTS PACK MANAGER');
  console.log('  ⚜️  ================================');
  console.log(`  🌐  Running at: http://localhost:${PORT}`);
  console.log(`  🔐  Admin password: cubmaster123`);
  console.log(`       (change this in Admin > Settings)`);
  console.log('  ================================');
  console.log('');
});
