// Parse bundled code without evaluating it. All replacements use UTF-16 offsets
// here, so non-BMP characters elsewhere in a bundle cannot shift an edit.
import { readFileSync } from 'node:fs';
import { parse } from './vendor/acorn/acorn.mjs';

function walk(node, visit, parent = null) {
  if (!node || typeof node.type !== 'string') return;
  visit(node, parent);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) for (const child of value) walk(child, visit, node);
    else if (value && typeof value.type === 'string') walk(value, visit, node);
  }
}
const name = node => node?.type === 'Identifier' ? node.name : node?.type === 'Literal' ? node.value : undefined;
const member = (node, key) => node?.type === 'MemberExpression' && !node.optional &&
  (node.computed ? node.property.type === 'Literal' : node.property.type === 'Identifier') && name(node.property) === key;
const propertyName = node => node.type === 'Property' && !node.method && node.kind === 'init' &&
  (!node.computed || node.key.type === 'Literal') ? name(node.key) : undefined;
const call = node => node?.type === 'CallExpression' && !node.optional;

function findMenu(tree, parents) {
  const found = [];
  walk(tree, node => {
    if (node.type !== 'AwaitExpression' || !call(node.argument)) return;
    const thunk = node.argument.arguments[0];
    if (node.argument.arguments.length !== 1 || !['ArrowFunctionExpression', 'FunctionExpression'].includes(thunk?.type) || thunk.params.length || thunk.async || thunk.generator) return;
    const body = thunk.body;
    const show = body.type === 'BlockStatement' && body.body.length === 1 && body.body[0].type === 'ReturnStatement' ? body.body[0].argument : body;
    if (!call(show) || !member(show.callee, 'show') || !member(show.callee.object, 'contextMenu')) return;
    const items = show.arguments[0];
    if (!call(items) || items.arguments.length !== 1 || items.arguments[0].type !== 'ObjectExpression') return;
    const options = items.arguments[0];
    const fields = new Map();
    for (const property of options.properties) {
      const key = propertyName(property);
      if (fields.has(key) && key !== undefined) throw Error('Duplicate native menu option');
      if (key !== undefined) fields.set(key, property.value);
    }
    if (!['canOperate', 'branch', 'snoozePresets'].every(key => fields.has(key))) return;
    let branch = fields.get('branch');
    if (branch.type === 'LogicalExpression' && branch.operator === '??') branch = branch.left;
    if (!member(branch, 'branch') || branch.object.type !== 'Identifier') return;
    const binding = parents.get(node);
    let statement, result;
    if (binding?.type === 'VariableDeclarator' && binding.id.type === 'Identifier') {
      statement = parents.get(binding);
      if (statement?.type !== 'VariableDeclaration' || statement.declarations.at(-1) !== binding) return;
      result = binding.id.name;
    } else if (binding?.type === 'AssignmentExpression' && binding.operator === '=' && binding.left.type === 'Identifier') {
      statement = parents.get(binding);
      if (statement?.type !== 'ExpressionStatement') return;
      result = binding.left.name;
    } else return;
    const container = parents.get(statement);
    if (!['Program', 'BlockStatement', 'SwitchCase'].includes(container?.type)) return;
    found.push({ items, options, statement, result, thread: branch.object.name });
  });
  if (found.length !== 1) throw Error(`native thread menu: expected one integration point, found ${found.length}`);
  return found[0];
}

function sumTerms(node) {
  return node.type === 'BinaryExpression' && node.operator === '+' ? [...sumTerms(node.left), ...sumTerms(node.right)] : [node];
}
function emptySidebar(tree) {
  const found = [];
  walk(tree, node => {
    if (node.type !== 'ConditionalExpression') return;
    let message = false;
    walk(node.consequent, child => {
      if (child.type === 'Literal' && child.value === 'No threads yet' ||
          child.type === 'TemplateLiteral' && child.expressions.length === 0 && child.quasis[0].value.cooked === 'No threads yet') message = true;
    });
    if (!message) return;
    walk(node.test, child => {
      if (child.type !== 'BinaryExpression' || !['===', '=='].includes(child.operator) || child.right.type !== 'Literal' || child.right.value !== 0) return;
      const terms = sumTerms(child.left);
      if (terms.length >= 2 && terms.some(term => member(term, 'length') && term.object.type === 'Identifier') &&
          terms.every(term => term.type === 'Identifier' || member(term, 'length') && term.object.type === 'Identifier')) found.push(child.left);
    });
  });
  if (found.length !== 1) throw Error(`empty sidebar message: expected one integration point, found ${found.length}`);
  return found[0];
}

try {
  const { source, mode } = JSON.parse(readFileSync(0, 'utf8'));
  const tree = parse(source, { ecmaVersion: 'latest', sourceType: 'module' });
  const parents = new WeakMap();
  walk(tree, (node, parent) => parents.set(node, parent));
  let output;
  if (mode === 'empty-sidebar') {
    const sum = emptySidebar(tree);
    output = source.slice(0, sum.start) + `(__t3PersistedRows.length+(${source.slice(sum.start, sum.end)}))` + source.slice(sum.end);
  } else {
    const menu = findMenu(tree, parents);
    if (mode === 'inspect-menu') output = {
      prefix: source.slice(0, menu.options.start), suffix: source.slice(menu.options.end),
      properties: menu.options.properties.map(property => source.slice(property.start, property.end)),
    };
    else if (mode === 'thread-menu') {
      const guard = `;if(${menu.result}._tag!==\`Failure\`&&__t3PersistedRuntime.isAction(${menu.result}.value)){await __t3PersistedRuntime.handle(${menu.result}.value,${menu.thread});return}`;
      output = source.slice(0, menu.items.start) + `__t3PersistedRuntime.menu(${source.slice(menu.items.start, menu.items.end)},${menu.thread})` +
        source.slice(menu.items.end, menu.statement.end) + guard + source.slice(menu.statement.end);
    } else throw Error('Unknown sidebar syntax operation');
  }
  process.stdout.write(JSON.stringify({ output }));
} catch (error) {
  process.stdout.write(JSON.stringify({ error: `Cannot analyze native thread menu/sidebar: ${error.message}` }));
  process.exitCode = 1;
}
