const express = require('express');
const router = express.Router();
const db = require('../db');
const { requireAdmin } = require('./auth');

function sanitizeFilename(str) {
  return str.replace(/[^a-z0-9_\-]/gi, '_').slice(0, 60);
}

function buildCSV(rows, headers) {
  const escape = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;
  return [headers, ...rows].map(row => row.map(escape).join(',')).join('\r\n');
}

// GET /api/exports/event/:id/csv
router.get('/event/:id/csv', requireAdmin, (req, res) => {
  const event = db.prepare('SELECT * FROM events WHERE id = ?').get(req.params.id);
  if (!event) return res.status(404).json({ error: 'Event not found' });

  const signups = db.prepare(`
    SELECT s.firstName, s.lastName, s.rank, s.den, s.grade,
           s.parentName, s.parentEmail, s.parentPhone,
           su.signupDate, su.notes
    FROM signups su JOIN scouts s ON su.scoutId = s.id
    WHERE su.eventId = ?
    ORDER BY s.rank, s.lastName, s.firstName
  `).all(req.params.id);

  const headers = ['First Name', 'Last Name', 'Rank', 'Den', 'Grade', 'Parent Name', 'Parent Email', 'Parent Phone', 'Signup Date', 'Notes'];
  const rows = signups.map(s => [
    s.firstName, s.lastName, s.rank, s.den, s.grade,
    s.parentName, s.parentEmail, s.parentPhone,
    s.signupDate ? s.signupDate.split('T')[0] : '',
    s.notes
  ]);

  const filename = `${sanitizeFilename(event.title)}_${event.date}_signups.csv`;
  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
  res.send(buildCSV(rows, headers));
});

// GET /api/exports/event/:id/pdf
router.get('/event/:id/pdf', requireAdmin, (req, res) => {
  const PDFDocument = require('pdfkit');
  const event = db.prepare('SELECT * FROM events WHERE id = ?').get(req.params.id);
  if (!event) return res.status(404).json({ error: 'Event not found' });

  const signups = db.prepare(`
    SELECT s.firstName, s.lastName, s.rank, s.den, s.grade,
           s.parentName, s.parentPhone
    FROM signups su JOIN scouts s ON su.scoutId = s.id
    WHERE su.eventId = ?
    ORDER BY s.rank, s.lastName, s.firstName
  `).all(req.params.id);

  const doc = new PDFDocument({ margin: 50, size: 'LETTER' });
  const filename = `${sanitizeFilename(event.title)}_roster.pdf`;

  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
  doc.pipe(res);

  // Title block
  doc.rect(0, 0, 612, 90).fill('#003F87');
  doc.fontSize(22).fillColor('#FCC200').font('Helvetica-Bold').text('CUB SCOUTS PACK MANAGER', 50, 18, { align: 'center' });
  doc.fontSize(14).fillColor('#ffffff').font('Helvetica').text('Event Sign-Up Roster', 50, 48, { align: 'center' });

  doc.moveDown(2);
  doc.fontSize(18).fillColor('#003F87').font('Helvetica-Bold').text(event.title, { align: 'center' });
  doc.moveDown(0.3);

  const dateStr = event.date + (event.time ? ' at ' + event.time : '');
  doc.fontSize(12).fillColor('#555').font('Helvetica').text(`Date: ${dateStr}`, { align: 'center' });
  if (event.location) doc.text(`Location: ${event.location}`, { align: 'center' });
  doc.text(`Total Scouts Signed Up: ${signups.length}`, { align: 'center' });

  doc.moveDown(1);
  doc.moveTo(50, doc.y).lineTo(562, doc.y).strokeColor('#003F87').lineWidth(2).stroke();
  doc.moveDown(0.8);

  if (signups.length === 0) {
    doc.fontSize(13).fillColor('#999').text('No scouts have signed up for this event yet.', { align: 'center' });
  } else {
    // Table header
    const cols = [
      { label: 'Scout Name', x: 50, w: 140 },
      { label: 'Rank', x: 190, w: 70 },
      { label: 'Den', x: 260, w: 50 },
      { label: 'Grade', x: 310, w: 60 },
      { label: 'Parent / Guardian', x: 370, w: 120 },
      { label: 'Phone', x: 490, w: 80 },
    ];

    const headerY = doc.y;
    doc.rect(45, headerY - 4, 522, 20).fill('#003F87');
    doc.font('Helvetica-Bold').fontSize(9).fillColor('#ffffff');
    cols.forEach(c => doc.text(c.label, c.x, headerY, { width: c.w, lineBreak: false }));
    doc.moveDown(1.2);

    signups.forEach((s, idx) => {
      if (doc.y > 700) {
        doc.addPage();
        doc.moveDown(1);
      }
      const rowY = doc.y;
      if (idx % 2 === 0) {
        doc.rect(45, rowY - 3, 522, 18).fill('#F0F4FF');
      }
      doc.font('Helvetica').fontSize(9).fillColor('#222');
      const values = [
        `${s.firstName} ${s.lastName}`,
        s.rank || '',
        s.den || '',
        s.grade || '',
        s.parentName || '',
        s.parentPhone || '',
      ];
      cols.forEach((c, i) => doc.text(values[i], c.x, rowY, { width: c.w - 4, lineBreak: false }));
      doc.moveDown(0.9);
    });

    doc.moveDown(1);
    doc.moveTo(50, doc.y).lineTo(562, doc.y).strokeColor('#ccc').lineWidth(1).stroke();
    doc.moveDown(0.5);
    doc.fontSize(9).fillColor('#999').text(`Generated ${new Date().toLocaleDateString()} — Cub Scouts Pack Manager`, { align: 'center' });
  }

  doc.end();
});

// GET /api/exports/scout/:id/pdf
router.get('/scout/:id/pdf', requireAdmin, (req, res) => {
  const PDFDocument = require('pdfkit');
  const scout = db.prepare('SELECT * FROM scouts WHERE id = ?').get(req.params.id);
  if (!scout) return res.status(404).json({ error: 'Scout not found' });

  const awards = db.prepare('SELECT * FROM awards WHERE scoutId = ? ORDER BY type, name').all(req.params.id);
  const events = db.prepare(`
    SELECT e.title, e.date, e.time, e.location
    FROM signups su JOIN events e ON su.eventId = e.id
    WHERE su.scoutId = ?
    ORDER BY e.date
  `).all(req.params.id);

  const RANK_COLORS_HEX = {
    Lion: '#7B2D8B', Tiger: '#EA580C', Wolf: '#6B7280',
    Bear: '#92400E', Webelos: '#059669', AOL: '#1D4ED8',
  };
  const rankColor = RANK_COLORS_HEX[scout.rank] || '#003F87';

  const doc = new PDFDocument({ margin: 50, size: 'LETTER' });
  const filename = `${sanitizeFilename(scout.firstName + '_' + scout.lastName)}_profile.pdf`;

  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', `attachment; filename="${filename}"`);
  doc.pipe(res);

  // Header
  doc.rect(0, 0, 612, 90).fill('#003F87');
  doc.fontSize(20).fillColor('#FCC200').font('Helvetica-Bold').text('CUB SCOUTS PACK MANAGER', 50, 18, { align: 'center' });
  doc.fontSize(12).fillColor('#ffffff').font('Helvetica').text('Scout Profile Report', 50, 48, { align: 'center' });

  doc.moveDown(2);
  doc.rect(45, doc.y, 522, 55).fill(rankColor + '20').stroke(rankColor);
  const boxY = doc.y + 8;
  doc.fontSize(22).fillColor(rankColor).font('Helvetica-Bold').text(`${scout.firstName} ${scout.lastName}`, 60, boxY);
  const rankLabel = scout.rank === 'AOL' ? 'Arrow of Light' : scout.rank;
  doc.fontSize(13).fillColor('#555').font('Helvetica').text(`${rankLabel} Scout${scout.den ? ' · ' + scout.den : ''}${scout.grade ? ' · ' + scout.grade : ''}`, 60, boxY + 26);
  doc.y = boxY + 60;
  doc.moveDown(0.5);

  if (scout.parentName || scout.parentEmail || scout.parentPhone) {
    doc.fontSize(10).fillColor('#333').font('Helvetica-Bold').text('Contact: ', { continued: true });
    doc.font('Helvetica').text([scout.parentName, scout.parentEmail, scout.parentPhone].filter(Boolean).join(' · '));
  }
  if (scout.dateJoined) {
    doc.fontSize(10).fillColor('#333').font('Helvetica-Bold').text('Joined: ', { continued: true });
    doc.font('Helvetica').text(scout.dateJoined);
  }
  doc.moveDown(1);

  // Awards summary
  const completed = awards.filter(a => a.status === 'completed');
  const inProgress = awards.filter(a => a.status === 'in_progress');
  const notStarted = awards.filter(a => a.status === 'not_started');

  // Summary boxes
  const summaries = [
    { label: 'Completed', count: completed.length, color: '#10B981', bg: '#ECFDF5' },
    { label: 'In Progress', count: inProgress.length, color: '#F59E0B', bg: '#FFFBEB' },
    { label: 'Not Started', count: notStarted.length, color: '#9CA3AF', bg: '#F9FAFB' },
  ];
  const bx = 50, bw = 168, bh = 45, bSpace = 3;
  summaries.forEach((s, i) => {
    const sx = bx + i * (bw + bSpace);
    doc.rect(sx, doc.y, bw, bh).fill(s.bg).strokeColor(s.color).lineWidth(1).stroke();
    doc.fontSize(22).fillColor(s.color).font('Helvetica-Bold').text(String(s.count), sx + 10, doc.y + 5, { width: bw - 20, align: 'center', lineBreak: false });
    doc.fontSize(10).fillColor(s.color).font('Helvetica').text(s.label, sx + 10, doc.y + 28, { width: bw - 20, align: 'center', lineBreak: false });
  });
  doc.y += bh + 15;
  doc.moveDown(0.5);

  const sectionHeader = (title, color) => {
    doc.rect(45, doc.y, 522, 22).fill(color);
    doc.fontSize(11).fillColor('#fff').font('Helvetica-Bold').text(title, 55, doc.y + 5);
    doc.moveDown(1.2);
  };

  const awardRow = (award, idx) => {
    if (doc.y > 700) { doc.addPage(); doc.moveDown(1); }
    const rowY = doc.y;
    if (idx % 2 === 0) doc.rect(45, rowY - 2, 522, 16).fill('#F9FAFB');
    doc.font('Helvetica').fontSize(9).fillColor('#222').text(`• ${award.name}`, 55, rowY, { width: 260, lineBreak: false });
    doc.text(award.type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()), 320, rowY, { width: 130, lineBreak: false });
    const statusLabel = award.status === 'completed' ? `Completed${award.dateEarned ? ' ' + award.dateEarned : ''}` : award.status === 'in_progress' ? `${award.progress}% complete` : 'Not started';
    const statusColor = award.status === 'completed' ? '#10B981' : award.status === 'in_progress' ? '#F59E0B' : '#9CA3AF';
    doc.fillColor(statusColor).text(statusLabel, 450, rowY, { width: 110, lineBreak: false });
    doc.moveDown(0.85);
  };

  if (completed.length > 0) {
    sectionHeader(`Completed Awards (${completed.length})`, '#059669');
    completed.forEach((a, i) => awardRow(a, i));
    doc.moveDown(0.5);
  }

  if (inProgress.length > 0) {
    sectionHeader(`In Progress (${inProgress.length})`, '#D97706');
    inProgress.forEach((a, i) => awardRow(a, i));
    doc.moveDown(0.5);
  }

  if (notStarted.length > 0) {
    sectionHeader(`Not Started (${notStarted.length})`, '#9CA3AF');
    notStarted.forEach((a, i) => awardRow(a, i));
    doc.moveDown(0.5);
  }

  // Events
  doc.moveDown(0.5);
  sectionHeader(`Registered Events (${events.length})`, '#003F87');
  if (events.length === 0) {
    doc.font('Helvetica').fontSize(10).fillColor('#999').text('No events registered.');
  } else {
    events.forEach((e, i) => {
      if (doc.y > 700) { doc.addPage(); doc.moveDown(1); }
      const rowY = doc.y;
      if (i % 2 === 0) doc.rect(45, rowY - 2, 522, 16).fill('#EFF6FF');
      doc.font('Helvetica').fontSize(9).fillColor('#222').text(`• ${e.title}`, 55, rowY, { width: 260, lineBreak: false });
      doc.text(e.date + (e.time ? ' at ' + e.time : ''), 320, rowY, { width: 150, lineBreak: false });
      if (e.location) doc.fillColor('#555').text(e.location, 470, rowY, { width: 100, lineBreak: false });
      doc.moveDown(0.85);
    });
  }

  doc.moveDown(1);
  doc.fontSize(8).fillColor('#999').text(`Generated ${new Date().toLocaleDateString()} — Cub Scouts Pack Manager`, { align: 'center' });

  doc.end();
});

// GET /api/exports/all-scouts/csv
router.get('/all-scouts/csv', requireAdmin, (req, res) => {
  const scouts = db.prepare('SELECT * FROM scouts ORDER BY rank, lastName, firstName').all();
  const headers = ['First Name', 'Last Name', 'Rank', 'Den', 'Grade', 'Date Joined', 'Parent Name', 'Parent Email', 'Parent Phone', 'Notes'];
  const rows = scouts.map(s => [s.firstName, s.lastName, s.rank, s.den, s.grade, s.dateJoined, s.parentName, s.parentEmail, s.parentPhone, s.notes]);
  res.setHeader('Content-Type', 'text/csv; charset=utf-8');
  res.setHeader('Content-Disposition', 'attachment; filename="all_scouts.csv"');
  res.send(buildCSV(rows, headers));
});

function buildCSV(rows, headers) {
  const escape = (v) => `"${String(v == null ? '' : v).replace(/"/g, '""')}"`;
  return [headers, ...rows].map(row => row.map(escape).join(',')).join('\r\n');
}

module.exports = router;
