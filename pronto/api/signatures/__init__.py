# -*- coding: utf-8 -*-

from flask import Blueprint


bp = Blueprint("api.signatures", __name__, url_prefix="/api/signatures")

from . import comments
from . import descriptions
from . import go
from . import proteins
from . import taxonomy