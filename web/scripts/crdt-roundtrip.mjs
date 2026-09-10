/**
 * Verifies that a Yjs update authored by the Python backend produces a document
 * that is valid against the TipTap schema the browser editor uses.
 *
 * This is the load-bearing check for the whole design: the AI writes into the
 * shared XmlFragment from Python, and the editor has to be able to render it.
 *
 * Usage: node scripts/crdt-roundtrip.mjs <file-containing-base64-update>
 * Prints the resulting ProseMirror JSON on success, exits non-zero on failure.
 */
import fs from 'node:fs'
import * as Y from 'yjs'
import { getSchema } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import { yXmlFragmentToProseMirrorRootNode } from '@tiptap/y-tiptap'

const path = process.argv[2]
if (!path) {
  console.error('usage: node scripts/crdt-roundtrip.mjs <base64-update-file>')
  process.exit(2)
}

const doc = new Y.Doc()
Y.applyUpdate(doc, Buffer.from(fs.readFileSync(path, 'utf8').trim(), 'base64'))

const fragment = doc.getXmlFragment('default')
const schema = getSchema([StarterKit])
const node = yXmlFragmentToProseMirrorRootNode(fragment, schema)

// Throws if the document violates the schema's content expressions.
node.check()

process.stdout.write(JSON.stringify(node.toJSON()))
