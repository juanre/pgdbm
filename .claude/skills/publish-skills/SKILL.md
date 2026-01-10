---
name: publish-skills
description: How to update and publish pgdbm skills for Claude Code users
---

# Publishing pgdbm Skills

## Overview

pgdbm provides skills for Claude Code via the `juanre-ai-tools` marketplace. This skill explains the structure and how to publish updates.

## Architecture

```
juanre-ai-tools (MARKETPLACE)
    └── marketplace.json references:
        └── juanre/pgdbm (GITHUB REPO)
            ├── skills/           ← Skills content lives here
            │   ├── testing-database-code/SKILL.md
            │   ├── common-mistakes/SKILL.md
            │   ├── choosing-pattern/SKILL.md
            │   └── ...
            └── .claude-plugin/
                └── plugin.json   ← Version controls caching
```

**Key points:**
- Skills for distribution live in `skills/` at repo root (NOT `.claude/skills/`)
- `.claude/skills/` is for LOCAL project skills (like this one)
- The marketplace.json in ai-tools just points to this repo
- `.claude-plugin/plugin.json` version determines when users get updates

## Updating Skills

### 1. Edit Skills

Skills are in `/skills/<skill-name>/SKILL.md`:

```
skills/
├── choosing-pattern/SKILL.md
├── common-mistakes/SKILL.md
├── core-api-reference/SKILL.md
├── dual-mode-library/SKILL.md
├── migrations-api-reference/SKILL.md
├── shared-pool-pattern/SKILL.md
├── standalone-service/SKILL.md
├── testing-database-code/SKILL.md
└── using-pgdbm/SKILL.md
```

### 2. Bump Plugin Version

**Critical**: Users only get updates when the version changes.

```bash
# Check current version
cat .claude-plugin/plugin.json | grep version

# Edit to bump version
# "version": "0.2.1" → "version": "0.2.2"
```

Keep plugin version in sync with library version in `pyproject.toml`.

### 3. Commit and Push

```bash
git add skills/ .claude-plugin/plugin.json
git commit -m "docs: update skills for X.Y.Z

- Description of skill changes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

git push origin main
```

### 4. Verify Update Available

```bash
# Check version on GitHub
curl -s https://api.github.com/repos/juanre/pgdbm/contents/.claude-plugin/plugin.json | jq -r '.content' | base64 -d | grep version
```

## How Users Get Updates

Users subscribed to `juanre-ai-tools` marketplace get the `pgdbm` plugin.

**Manual update:**
```bash
claude plugin update pgdbm@juanre-ai-tools
```

**Auto-update**: Disabled by default for third-party marketplaces. Users can enable via `/plugin` → Marketplaces → Enable auto-update.

## Testing Locally

After pushing, test the update:

```bash
# Update plugin
claude plugin update pgdbm@juanre-ai-tools

# Verify new version cached
ls ~/.claude/plugins/cache/juanre-ai-tools/pgdbm/

# Check skill content
head -30 ~/.claude/plugins/cache/juanre-ai-tools/pgdbm/*/skills/testing-database-code/SKILL.md
```

## Skill File Format

Each skill needs YAML frontmatter:

```markdown
---
name: skill-name
description: One-line description used for skill discovery
---

# Skill Title

## Overview

Brief explanation of what this skill covers.

## Content

The actual guidance...
```

## Marketplace Entry

The `juanre-ai-tools` marketplace.json has entries like:

```json
{
  "name": "pgdbm",
  "source": {
    "source": "github",
    "repo": "juanre/pgdbm"
  },
  "description": "...",
  "version": "1.0.0"  ← This is the LISTING version, not the plugin version
}
```

The listing version (1.0.0) is independent of the plugin version. The plugin version in `.claude-plugin/plugin.json` is what matters for caching.

## Related Skills

- For library releases: See `release` skill
