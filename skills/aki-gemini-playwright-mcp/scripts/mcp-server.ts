import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import path from 'node:path';
import process from 'node:process';
import { generateImage } from './gemini-playwright.ts';

const server = new McpServer({
  name: 'Aki Gemini Playwright MCP',
  version: '0.1.0',
});

const GenerateSchema = z.object({
  prompt: z.string().min(1),
  outputPath: z.string().optional(),
  profileDir: z.string().optional(),
  headless: z.boolean().optional(),
  timeoutMs: z.number().optional(),
  keepOpen: z.boolean().optional(),
});

server.tool('generateGeminiImage', 'Generate an image via Gemini web using Playwright.', GenerateSchema, async (params) => {
  const outputPath = params.outputPath
    || path.join(process.cwd(), 'gemini-image.png');

  const result = await generateImage({
    prompt: params.prompt,
    outputPath,
    profileDir: params.profileDir || '',
    headless: params.headless ?? false,
    timeoutMs: params.timeoutMs ?? 180_000,
    keepOpen: params.keepOpen ?? false,
  });

  return {
    content: [
      { type: 'text', text: `Saved image to ${result.outputPath}` },
      { type: 'text', text: `Source URL: ${result.imageUrl}` },
    ],
  };
});

async function main(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
