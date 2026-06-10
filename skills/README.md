# pkflow skills

Agent skills for using pkflow. Each subdirectory is one skill (a `SKILL.md`
with YAML frontmatter + instructions).

## Available skills

- **[pkflow](pkflow/SKILL.md)** — run and diagnose NONMEM population PK/PD models
  from the command line: fit, GOF, VPC, bootstrap, shrinkage, η-covariate plots,
  model comparison, and reports.

## Installing for Claude Code

Copy (or symlink) a skill into your skills directory:

```bash
# user-level (all projects)
mkdir -p ~/.claude/skills
cp -r skills/pkflow ~/.claude/skills/

# or project-level
mkdir -p .claude/skills
cp -r skills/pkflow .claude/skills/
```

The skill activates automatically when a task matches its `description`
(NONMEM modeling, GOF/VPC/shrinkage, model comparison or reports).
