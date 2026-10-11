const fs = require('node:fs');
const path = require('node:path');

function validate(document) {
  if (!document || document.version !== 1 || typeof document.collapsed !== 'boolean' || !Array.isArray(document.members)) {
    throw new Error('Persisted membership file has an unsupported format. It was left untouched.');
  }
  const seen = new Set();
  for (const member of document.members) {
    validateRef(member);
    if (typeof member.addedAt !== 'string') throw new Error('Invalid Persisted membership date.');
    const key = JSON.stringify([member.environmentId, member.threadId]);
    if (seen.has(key)) throw new Error('Duplicate Persisted membership.');
    seen.add(key);
  }
  return document;
}

function validateRef(ref) {
  if (!ref || !['environmentId', 'threadId'].every(key => typeof ref[key] === 'string' && ref[key].length > 0 && ref[key].length <= 256)) {
    throw new Error('Invalid thread reference.');
  }
}

class Store {
  constructor(directory) {
    this.directory = directory;
    this.file = path.join(directory, 'membership.json');
  }

  readDocument() {
    try {
      return validate(JSON.parse(fs.readFileSync(this.file, 'utf8')));
    } catch (error) {
      if (error.code === 'ENOENT') return { version: 1, collapsed: false, members: [] };
      throw error;
    }
  }

  read() {
    try {
      return { enabled: true, ...this.readDocument() };
    } catch (error) {
      return { enabled: false, version: 1, collapsed: false, members: [], error: error.message };
    }
  }

  update(operation) {
    const document = this.readDocument();
    if (operation.type === 'collapse') {
      if (typeof operation.collapsed !== 'boolean') throw new Error('Invalid collapse state.');
      document.collapsed = operation.collapsed;
    } else if (operation.type === 'add' || operation.type === 'remove') {
      validateRef(operation.ref);
      const matches = member => member.environmentId === operation.ref.environmentId && member.threadId === operation.ref.threadId;
      if (operation.type === 'add' && !document.members.some(matches)) {
        document.members.push({ ...operation.ref, addedAt: new Date().toISOString() });
      } else if (operation.type === 'remove') {
        document.members = document.members.filter(member => !matches(member));
      }
    } else {
      throw new Error('Unsupported Persisted operation.');
    }
    fs.mkdirSync(this.directory, { recursive: true, mode: 0o700 });
    const temporary = this.file + '.' + process.pid + '.tmp';
    const data = JSON.stringify(validate(document), null, 2) + '\n';
    let descriptor;
    try {
      descriptor = fs.openSync(temporary, 'w', 0o600);
      fs.writeFileSync(descriptor, data);
      fs.fsyncSync(descriptor);
      fs.closeSync(descriptor);
      descriptor = undefined;
      if (fs.existsSync(this.file)) fs.copyFileSync(this.file, this.file + '.bak');
      fs.renameSync(temporary, this.file);
      const directoryFd = fs.openSync(this.directory, 'r');
      try { fs.fsyncSync(directoryFd); } finally { fs.closeSync(directoryFd); }
    } finally {
      if (descriptor !== undefined) fs.closeSync(descriptor);
      if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
    }
    return this.read();
  }
}

module.exports = { Store };
