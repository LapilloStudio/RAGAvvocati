// Document text extraction + chunking, all in JavaScript (runs in the nodejs
// route handler, no Python backend). PDF → page-aware chunks (so citations can
// reference a page); DOCX/XLSX → page-less chunks.

import { RecursiveCharacterTextSplitter } from "@langchain/textsplitters";
import mammoth from "mammoth";
import * as XLSX from "xlsx";

export interface Chunk {
  content: string;
  page: number | null;
}

const splitter = new RecursiveCharacterTextSplitter({
  chunkSize: 1000,
  chunkOverlap: 200,
});

/** Extract and chunk a PDF/DOCX/XLSX File into retrievable pieces. */
export async function extractChunks(file: File): Promise<Chunk[]> {
  const name = file.name.toLowerCase();
  const type = file.type;

  if (name.endsWith(".pdf") || type === "application/pdf") {
    return chunkPdf(file);
  }
  if (
    name.endsWith(".docx") ||
    type ===
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ) {
    const buffer = Buffer.from(await file.arrayBuffer());
    const { value } = await mammoth.extractRawText({ buffer });
    return chunkText(value, null);
  }
  if (
    name.endsWith(".xlsx") ||
    type ===
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
  ) {
    const buffer = Buffer.from(await file.arrayBuffer());
    return chunkXlsx(buffer);
  }

  throw new Error("Formato non supportato. Carica un file PDF, DOCX o XLSX.");
}

async function chunkPdf(file: File): Promise<Chunk[]> {
  // Dynamic import so Next.js doesn't bundle pdfjs-dist (serverExternalPackages).
  // GlobalWorkerOptions.workerSrc = "" disables the web-worker (not needed in Node.js).
  const { getDocument, GlobalWorkerOptions } = await import("pdfjs-dist");
  GlobalWorkerOptions.workerSrc = "";

  const buffer = await file.arrayBuffer();
  const pdf = await getDocument({ data: buffer }).promise;
  const out: Chunk[] = [];

  for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
    const page = await pdf.getPage(pageNum);
    const tc = await page.getTextContent();
    const text = (tc.items as Array<{ str?: string }>)
      .map((it) => it.str ?? "")
      .join(" ");
    for (const piece of await splitter.splitText(text)) {
      const content = piece.trim();
      if (content) out.push({ content, page: pageNum });
    }
  }
  return out;
}

async function chunkXlsx(buffer: Buffer): Promise<Chunk[]> {
  const wb = XLSX.read(buffer, { type: "buffer" });
  const out: Chunk[] = [];
  for (const sheetName of wb.SheetNames) {
    const csv = XLSX.utils.sheet_to_csv(wb.Sheets[sheetName]);
    const chunks = await chunkText(`Foglio "${sheetName}"\n${csv}`, null);
    out.push(...chunks);
  }
  return out;
}

async function chunkText(text: string, page: number | null): Promise<Chunk[]> {
  const pieces = await splitter.splitText(text);
  return pieces
    .map((p) => ({ content: p.trim(), page }))
    .filter((c) => c.content.length > 0);
}
