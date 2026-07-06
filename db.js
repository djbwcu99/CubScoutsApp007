const Database = require('better-sqlite3');
const bcrypt = require('bcryptjs');
const path = require('path');

const db = new Database(path.join(__dirname, 'scouts.db'));

db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

function initDB() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS scouts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      firstName TEXT NOT NULL,
      lastName TEXT NOT NULL,
      rank TEXT NOT NULL,
      den TEXT,
      grade TEXT,
      dateJoined TEXT,
      parentName TEXT,
      parentEmail TEXT,
      parentPhone TEXT,
      notes TEXT,
      createdAt TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS awards (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scoutId INTEGER NOT NULL,
      name TEXT NOT NULL,
      type TEXT NOT NULL,
      status TEXT DEFAULT 'not_started',
      progress INTEGER DEFAULT 0,
      dateEarned TEXT,
      notes TEXT,
      createdAt TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (scoutId) REFERENCES scouts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      date TEXT NOT NULL,
      time TEXT,
      location TEXT,
      description TEXT,
      maxSignups INTEGER DEFAULT NULL,
      createdAt TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS signups (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scoutId INTEGER NOT NULL,
      eventId INTEGER NOT NULL,
      signupDate TEXT DEFAULT (datetime('now')),
      notes TEXT,
      FOREIGN KEY (scoutId) REFERENCES scouts(id) ON DELETE CASCADE,
      FOREIGN KEY (eventId) REFERENCES events(id) ON DELETE CASCADE,
      UNIQUE(scoutId, eventId)
    );

    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY,
      value TEXT
    );
  `);

  // Set default admin password if not set
  const existing = db.prepare("SELECT value FROM settings WHERE key = 'admin_password'").get();
  if (!existing) {
    const hash = bcrypt.hashSync('cubmaster123', 10);
    db.prepare("INSERT INTO settings (key, value) VALUES ('admin_password', ?)").run(hash);
  }

  // Seed sample data if scouts table is empty
  const count = db.prepare('SELECT COUNT(*) as cnt FROM scouts').get();
  if (count.cnt === 0) {
    seedSampleData();
  }
}

function seedSampleData() {
  console.log('🌱 Seeding sample data...');

  const insertScout = db.prepare(
    'INSERT INTO scouts (firstName, lastName, rank, den, grade, dateJoined, parentName, parentEmail, parentPhone) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
  );
  const insertAward = db.prepare(
    'INSERT INTO awards (scoutId, name, type, status, progress, dateEarned) VALUES (?, ?, ?, ?, ?, ?)'
  );
  const insertEvent = db.prepare(
    'INSERT INTO events (title, date, time, location, description) VALUES (?, ?, ?, ?, ?)'
  );
  const insertSignup = db.prepare(
    'INSERT OR IGNORE INTO signups (scoutId, eventId) VALUES (?, ?)'
  );

  const seed = db.transaction(() => {
    // Scouts
    const s1 = insertScout.run('Liam', 'Johnson', 'Lion', 'Den 1', 'Kindergarten', '2024-09-01', 'Mark Johnson', 'mark.j@email.com', '555-1001').lastInsertRowid;
    const s2 = insertScout.run('Emma', 'Williams', 'Tiger', 'Den 2', '1st Grade', '2024-09-01', 'Sarah Williams', 'sarah.w@email.com', '555-1002').lastInsertRowid;
    const s3 = insertScout.run('Noah', 'Brown', 'Tiger', 'Den 2', '1st Grade', '2024-09-01', 'Chris Brown', 'chris.b@email.com', '555-1003').lastInsertRowid;
    const s4 = insertScout.run('Olivia', 'Davis', 'Wolf', 'Den 3', '2nd Grade', '2023-09-01', 'Amy Davis', 'amy.d@email.com', '555-1004').lastInsertRowid;
    const s5 = insertScout.run('Ethan', 'Martinez', 'Wolf', 'Den 3', '2nd Grade', '2023-09-01', 'Carlos Martinez', 'carlos.m@email.com', '555-1005').lastInsertRowid;
    const s6 = insertScout.run('Ava', 'Taylor', 'Bear', 'Den 4', '3rd Grade', '2022-09-01', 'James Taylor', 'james.t@email.com', '555-1006').lastInsertRowid;
    const s7 = insertScout.run('Mason', 'Anderson', 'Bear', 'Den 4', '3rd Grade', '2022-09-01', 'Lisa Anderson', 'lisa.a@email.com', '555-1007').lastInsertRowid;
    const s8 = insertScout.run('Sophia', 'Thomas', 'Webelos', 'Den 5', '4th Grade', '2021-09-01', 'David Thomas', 'david.t@email.com', '555-1008').lastInsertRowid;
    const s9 = insertScout.run('Lucas', 'Jackson', 'AOL', 'Den 6', '5th Grade', '2020-09-01', 'Karen Jackson', 'karen.j@email.com', '555-1009').lastInsertRowid;
    const s10 = insertScout.run('Isabella', 'White', 'AOL', 'Den 6', '5th Grade', '2020-09-01', 'Tom White', 'tom.w@email.com', '555-1010').lastInsertRowid;

    // Awards for scouts
    // Lion - Liam
    insertAward.run(s1, 'Lion Badge', 'rank_badge', 'in_progress', 60, null);
    insertAward.run(s1, 'Animal Kingdom Adventure', 'required_adventure', 'completed', 100, '2024-11-15');
    insertAward.run(s1, 'Big Cats', 'elective_adventure', 'in_progress', 40, null);
    insertAward.run(s1, 'Gizmos and Gadgets', 'elective_adventure', 'not_started', 0, null);

    // Tiger - Emma
    insertAward.run(s2, 'Tiger Badge', 'rank_badge', 'in_progress', 75, null);
    insertAward.run(s2, 'Tiger Bites', 'required_adventure', 'completed', 100, '2024-12-01');
    insertAward.run(s2, 'Earn Your Stripes', 'elective_adventure', 'in_progress', 50, null);
    insertAward.run(s2, 'Movin\' On', 'elective_adventure', 'completed', 100, '2025-01-20');

    // Tiger - Noah
    insertAward.run(s3, 'Tiger Badge', 'rank_badge', 'in_progress', 30, null);
    insertAward.run(s3, 'Tiger Bites', 'required_adventure', 'in_progress', 60, null);
    insertAward.run(s3, 'Sky is the Limit', 'elective_adventure', 'not_started', 0, null);

    // Wolf - Olivia
    insertAward.run(s4, 'Wolf Badge', 'rank_badge', 'completed', 100, '2024-05-10');
    insertAward.run(s4, 'Call of the Wild', 'required_adventure', 'completed', 100, '2024-03-12');
    insertAward.run(s4, 'Paws on the Path', 'required_adventure', 'completed', 100, '2024-04-01');
    insertAward.run(s4, 'Code of the Wolf', 'elective_adventure', 'completed', 100, '2024-04-20');
    insertAward.run(s4, 'Finding Your Way', 'elective_adventure', 'in_progress', 80, null);

    // Wolf - Ethan
    insertAward.run(s5, 'Wolf Badge', 'rank_badge', 'in_progress', 55, null);
    insertAward.run(s5, 'Call of the Wild', 'required_adventure', 'completed', 100, '2024-06-01');
    insertAward.run(s5, 'Howling at the Moon', 'required_adventure', 'in_progress', 70, null);
    insertAward.run(s5, 'Adventures in Coins', 'elective_adventure', 'not_started', 0, null);

    // Bear - Ava
    insertAward.run(s6, 'Bear Badge', 'rank_badge', 'completed', 100, '2024-05-15');
    insertAward.run(s6, 'Bear Claws', 'required_adventure', 'completed', 100, '2024-02-28');
    insertAward.run(s6, 'Bear Necessities', 'required_adventure', 'completed', 100, '2024-03-15');
    insertAward.run(s6, 'Baloo the Builder', 'elective_adventure', 'completed', 100, '2024-04-10');
    insertAward.run(s6, 'Super Science', 'elective_adventure', 'in_progress', 90, null);

    // Bear - Mason
    insertAward.run(s7, 'Bear Badge', 'rank_badge', 'in_progress', 45, null);
    insertAward.run(s7, 'Bear Claws', 'required_adventure', 'in_progress', 60, null);
    insertAward.run(s7, 'Robotics', 'elective_adventure', 'in_progress', 30, null);
    insertAward.run(s7, 'Beat of the Drum', 'elective_adventure', 'not_started', 0, null);

    // Webelos - Sophia
    insertAward.run(s8, 'Webelos Badge', 'rank_badge', 'in_progress', 85, null);
    insertAward.run(s8, 'Stronger, Faster, Higher', 'required_adventure', 'completed', 100, '2024-11-01');
    insertAward.run(s8, 'First Responder', 'required_adventure', 'completed', 100, '2024-10-15');
    insertAward.run(s8, 'Engineer', 'elective_adventure', 'in_progress', 70, null);
    insertAward.run(s8, 'Game Design', 'elective_adventure', 'completed', 100, '2025-01-05');

    // AOL - Lucas
    insertAward.run(s9, 'Arrow of Light Badge', 'rank_badge', 'in_progress', 90, null);
    insertAward.run(s9, 'Building a Better World', 'required_adventure', 'completed', 100, '2025-01-10');
    insertAward.run(s9, 'Scouting Adventure', 'required_adventure', 'completed', 100, '2025-01-20');
    insertAward.run(s9, 'Camper', 'elective_adventure', 'completed', 100, '2024-12-05');
    insertAward.run(s9, 'First Aid', 'elective_adventure', 'in_progress', 50, null);

    // AOL - Isabella
    insertAward.run(s10, 'Arrow of Light Badge', 'rank_badge', 'completed', 100, '2025-02-01');
    insertAward.run(s10, 'Building a Better World', 'required_adventure', 'completed', 100, '2024-11-30');
    insertAward.run(s10, 'Duty to God and Country', 'required_adventure', 'completed', 100, '2024-12-15');
    insertAward.run(s10, 'Scouting Adventure', 'required_adventure', 'completed', 100, '2025-01-10');
    insertAward.run(s10, 'Cyclist', 'elective_adventure', 'completed', 100, '2025-01-25');

    // Events
    const today = new Date();
    const fmt = (d) => d.toISOString().split('T')[0];
    const addDays = (d, n) => { const r = new Date(d); r.setDate(r.getDate() + n); return r; };

    const e1 = insertEvent.run('Pack Meeting - April', fmt(addDays(today, 5)), '6:30 PM', 'Community Center, Rm 101', 'Monthly pack meeting. All scouts and families welcome.').lastInsertRowid;
    const e2 = insertEvent.run('Pinewood Derby', fmt(addDays(today, 12)), '10:00 AM', 'Main Gymnasium', 'Annual Pinewood Derby race! Car check-in starts at 9 AM.').lastInsertRowid;
    const e3 = insertEvent.run('Camping Trip', fmt(addDays(today, 18)), '8:00 AM', 'Eagle Creek Campground', 'Two-night camping trip. Bring full gear.').lastInsertRowid;
    const e4 = insertEvent.run('Service Project - Park Cleanup', fmt(addDays(today, 25)), '9:00 AM', 'Riverside Park', 'Community service hour - pack gloves and work clothes.').lastInsertRowid;
    const e5 = insertEvent.run('Blue & Gold Banquet', fmt(addDays(today, 35)), '5:00 PM', 'Elk Lodge Hall', 'Annual Blue & Gold Banquet celebrating Scouting\'s anniversary.').lastInsertRowid;
    const e6 = insertEvent.run('STEM Day', fmt(addDays(today, -5)), '1:00 PM', 'Public Library', 'Fun STEM activities with experiments and robotics.').lastInsertRowid;

    // Signups
    insertSignup.run(s1, e1); insertSignup.run(s2, e1); insertSignup.run(s3, e1);
    insertSignup.run(s4, e1); insertSignup.run(s5, e1); insertSignup.run(s6, e1);
    insertSignup.run(s7, e1); insertSignup.run(s8, e1); insertSignup.run(s9, e1);
    insertSignup.run(s2, e2); insertSignup.run(s4, e2); insertSignup.run(s6, e2); insertSignup.run(s8, e2); insertSignup.run(s9, e2);
    insertSignup.run(s1, e3); insertSignup.run(s3, e3); insertSignup.run(s5, e3); insertSignup.run(s7, e3);
    insertSignup.run(s9, e4); insertSignup.run(s10, e4); insertSignup.run(s8, e4);
    insertSignup.run(s2, e6); insertSignup.run(s4, e6); insertSignup.run(s8, e6); insertSignup.run(s10, e6);
  });

  seed();
  console.log('✅ Sample data seeded!');
}

initDB();
module.exports = db;
