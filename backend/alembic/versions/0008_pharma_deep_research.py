"""Account-owned, recoverable Pharma research jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('pharma_deep_research',
        sa.Column('id',postgresql.UUID(as_uuid=True),primary_key=True),
        sa.Column('owner_id',postgresql.UUID(as_uuid=True),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('query',sa.Text(),nullable=False),sa.Column('status',sa.String(24),nullable=False),
        sa.Column('stage',sa.String(24),nullable=False),sa.Column('plan',postgresql.JSONB(),nullable=False),
        sa.Column('checkpoint',postgresql.JSONB(),nullable=False),sa.Column('activity',postgresql.JSONB(),nullable=False),
        sa.Column('report',postgresql.JSONB()),sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('lease_owner',sa.String(36)),sa.Column('lease_until',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('started_at',sa.DateTime(timezone=True)),sa.Column('completed_at',sa.DateTime(timezone=True)),
        sa.Column('queued_at',sa.DateTime(timezone=True)),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index('ix_pharma_deep_owner_created','pharma_deep_research',['owner_id','created_at'])
    op.create_index('ix_pharma_deep_queue','pharma_deep_research',['status','lease_until','created_at'])

def downgrade():
    op.drop_table('pharma_deep_research')
