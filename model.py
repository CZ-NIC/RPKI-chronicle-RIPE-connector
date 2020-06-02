# coding: utf-8
import datetime

from sqlalchemy import Column, ForeignKey, BigInteger, Integer, PrimaryKeyConstraint, MetaData, ForeignKey, SmallInteger, DateTime, TIMESTAMP, Boolean, Text, func, CHAR
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql.base import CIDR
from sqlalchemy.schema import FetchedValue


from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from dbconn import SQLALCHEMY_DATABASE_URI

engine = create_engine(SQLALCHEMY_DATABASE_URI)
Session = sessionmaker(bind=engine)

Base = declarative_base()


# status row in Conflict constants
RPKI_UNKNOWN = 0
RPKI_VALID = 1
RPKI_INVALID_ASN = 2
RPKI_INVALID_LENGTH = 3

class Conflict(Base):
    __tablename__ = 'conflict'
    __table_args__ = (
        PrimaryKeyConstraint('prefix_asn_id', 'status', 'start'),
    )
    prefix_asn_id = Column('prefix_asn_id', ForeignKey('prefix_asn.id', ondelete='CASCADE', onupdate='CASCADE'), nullable=False, index=True)
    status = Column('status', SmallInteger, nullable=False)
    start = Column('start', DateTime, nullable=False, default=None)
    end = Column('end', DateTime, nullable=True, default=None)

class PrefixAsn(Base):
    __tablename__ = 'prefix_asn'
    id = Column(Integer, primary_key=True, server_default=FetchedValue())
    prefix = Column(CIDR, nullable=False)
    asn = Column(BigInteger, nullable=False)
    cc = Column(CHAR, nullable=True)
    conflicts = relationship('Conflict', backref=__tablename__, lazy=True)

class Statistic(Base):
    __tablename__ = 'stats'
    ts = Column('ts', DateTime, primary_key=True)
    unknown = Column('unknown', Integer, nullable=False)
    valid = Column('valid', Integer, nullable=False)
    invalid_asn = Column('inval_asn', Integer, nullable=False)
    invalid_pfxlen = Column('inval_pxflen', Integer, nullable=False)


Base.metadata.create_all(engine)

