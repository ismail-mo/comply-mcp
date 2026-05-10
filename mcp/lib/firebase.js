import { config } from "dotenv";
config({ path: new URL("../../.env", import.meta.url).pathname });
import { initializeApp, cert, getApps } from "firebase-admin/app";
import { getFirestore, FieldValue } from "firebase-admin/firestore";
import { createRequire } from "module";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const serviceAccount = require(join(__dirname, "../../firebase-key.json"));

if (!getApps().length) {
  initializeApp({ credential: cert(serviceAccount) });
}

export const db = getFirestore();

const GEMINI_EMBED_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key=${process.env.GOOGLE_API_KEY}`;

export async function embedQuery(text) {
  const res = await fetch(GEMINI_EMBED_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "models/gemini-embedding-001",
      content: { parts: [{ text }] },
      taskType: "RETRIEVAL_QUERY",
      outputDimensionality: 1536,
    }),
  });
  if (!res.ok) throw new Error(`Embed API ${res.status}: ${await res.text()}`);
  const json = await res.json();
  return json.embedding.values;
}

export async function vectorSearch(collectionName, queryVector, topK = 5) {
  const snapshot = await db
    .collection(collectionName)
    .findNearest("embedding", FieldValue.vector(queryVector), {
      limit: topK,
      distanceMeasure: "COSINE",
    })
    .get();

  return snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
}
