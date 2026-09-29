# Resollo agent skills

[Agent Skills](https://agentskills.io) for working with [Resollo](https://www.resollo.com), the AI-assisted international marketplace, from any skills-compatible AI agent (Claude, Claude Code, Codex, Gemini CLI, Cursor, and others).

| Skill | What it does |
|---|---|
| [`resollo-selling`](resollo-selling/SKILL.md) | Photos → cleaned-up product shots → inactive draft listing that Resollo's own AI fills in. Plus managing listings, offers and orders as a seller. |
| [`resollo-buying`](resollo-buying/SKILL.md) | Search across countries and currencies, check sellers and reviews, ask questions, negotiate, place orders, all with explicit user approval at every binding step. |

Both skills run on Resollo's MCP server, `https://www.resollo.com/api/mcp`. Reading is open. Selling, offers and orders need a personal API key from your Resollo profile ("AI Agent Access"), sent as `Authorization: Bearer <key>`.

The photo clean-up in `resollo-selling` uses the free local MCP servers in this repository: [`bgremoval-mcp`](../bgremoval-mcp/), [`gimp-mcp`](../gimp-mcp/) and [`inkscape-mcp`](../inkscape-mcp/).

## Install

Copy a skill folder into your agent's skills directory, for example `~/.claude/skills/` for Claude Code, or see your agent's documentation.

## Safety by design

- Listings are always created **inactive**; the seller activates them.
- Orders need `confirm: true`, sent only after the user approves the summary.
- Resollo never processes payments; card payments go through a Stripe link the user opens.
- No free-text addresses: saved addresses or personal pickup only.

## License

MIT, like the rest of this repository.
