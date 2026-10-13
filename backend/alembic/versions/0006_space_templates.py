"""Spaces remember their template, which decides their agent's tools. Additive only.

Existing Spaces created from a template are recognized by unchanged template instructions or the template's own
name. The identifiers below are frozen here so later edits to templates cannot change what this migration does.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = depends_on = None

# (template id, template name, start of its original instructions)
TEMPLATES = (
    ("tpl_market_access", "Market Access & Pricing", "You are a senior market access analyst. Lead with the answer"),
    ("tpl_competitive", "Competitive Intelligence", "Act as a competitive intelligence analyst. For each competitor"),
    ("tpl_regulatory", "Regulatory Watch", "Summarize regulatory decisions and guidance precisely: agency"),
    ("tpl_research", "Research Assistant", "Provide detailed, well-sourced answers. Cite peer-reviewed papers"),
    ("tpl_data", "Data Analyst", "Explain methodology and assumptions before conclusions. Use precise statistical"),
    ("tpl_patents", "Patent Researcher", "For each patent give the number, title, filing and priority dates"),
    ("tpl_study", "Study Guide", "Create study guides with clear headings, key definitions and short summaries"),
    ("tpl_tutor", "Tutor", "Act as a patient tutor. Break topics into small steps"),
    ("tpl_code", "Code Helper", "Give complete, working code using current best practices"),
    ("tpl_writing", "Writing Coach", "Give specific, constructive feedback rather than praise"),
    ("tpl_trip", "Trip Planner", "Ask for budget, dates, interests and group size if they are missing"),
)


def upgrade():
    op.add_column("spaces", sa.Column("template", sa.String(40), nullable=True))
    spaces = sa.table("spaces", sa.column("template", sa.String), sa.column("name", sa.String),
                      sa.column("custom_instructions", sa.Text))
    for template_id, name, opening in TEMPLATES:
        op.execute(spaces.update()
                   .where(spaces.c.template.is_(None))
                   .where(sa.or_(spaces.c.custom_instructions.like(opening + "%"),
                                 sa.func.lower(sa.func.trim(spaces.c.name)) == name.lower()))
                   .values(template=template_id))


def downgrade():
    op.drop_column("spaces", "template")
