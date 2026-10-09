"""An MCP server next to a REST API: one FastMCP instance mounted into the FastAPI app, its tools
thin wrappers over the service layer the REST routes use too.

A support-ticket service whose agents suggest a ticket's category, priority and team for a person
to approve. FastMCP 4 on MCP SDK 2. The store is a dict so the example runs on its own; in a
project it is the database.
"""

import functools
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal, ParamSpec, TypeVar

from fastapi import FastAPI, HTTPException
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- config

# A limit the tool description mentions comes from here, so the text and the behaviour agree.
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "20"))

# --------------------------------------------------------------------------- service layer
# Typed inputs, typed results, domain exceptions. REST and MCP both call these; neither has
# business logic of its own.


class NotFound(Exception):
    pass


Value = str | int | None


class Ticket(BaseModel):
    ticket_id: str = Field(description="Six-digit ticket number, e.g. '000042'.")
    title: str
    fields: dict[str, Value] = Field(description="category, priority and team; null where not set yet.")


class TicketPage(BaseModel):
    tickets: list[Ticket]
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page; null on the last page.")
    note: str | None = Field(default=None, description="Says how to narrow the query when results were cut.")


class Skipped(BaseModel):
    field: str
    reason: Literal["unknown_field", "approved", "invalid_value"]
    detail: str


class SuggestResult(BaseModel):
    ticket_id: str
    written: list[str] = Field(description="Fields that now hold the suggested value, awaiting approval.")
    skipped: list[Skipped] = Field(description="Fields that were not written, each with its reason.")


class FieldCheck(BaseModel):
    ok: bool
    value: Value = Field(description="The value as the ticket system stores it.")
    errors: list[str]


class Validation(BaseModel):
    ok: bool
    fields: dict[str, FieldCheck]


CATEGORIES = ("access", "billing", "bug", "other")
STORE: dict[str, Ticket] = {
    "000041": Ticket(ticket_id="000041", title="Login fails after password reset", fields={"category": "access", "priority": 2, "team": "identity"}),
    "000042": Ticket(ticket_id="000042", title="Login page loads slowly", fields={"category": None, "priority": None, "team": None}),
}
APPROVED: set[tuple[str, str]] = {("000041", "priority")}


def normalize_id(ticket_id: str) -> str:
    """Identifiers are read leniently: '42' and '000042' name the same ticket."""
    return ticket_id.strip().zfill(6)


def get_ticket(ticket_id: str) -> Ticket:
    ticket_id = normalize_id(ticket_id)
    if ticket_id not in STORE:
        raise NotFound(f"There is no ticket {ticket_id}.")
    return STORE[ticket_id]


def search_tickets(query: str, limit: int, cursor: str | None) -> TicketPage:
    hits = [t for t in STORE.values() if query.lower() in t.title.lower()]
    start = int(cursor or 0)
    more = start + limit < len(hits)
    return TicketPage(
        tickets=hits[start : start + limit],
        next_cursor=str(start + limit) if more else None,
        note=f"{len(hits)} tickets match; narrow the query or page with cursor." if more else None,
    )


def check_value(field: str, value: object) -> FieldCheck:
    """Validates exactly as the ticket system stores values: no conversions beyond what it accepts."""
    if field == "category":
        ok = value in CATEGORIES
        return FieldCheck(ok=ok, value=value if ok else None, errors=[] if ok else [f"category is one of {', '.join(CATEGORIES)}."])
    if field == "priority":
        ok = isinstance(value, int) and 1 <= value <= 4
        return FieldCheck(ok=ok, value=value if ok else None, errors=[] if ok else ["priority is a whole number from 1 to 4."])
    if field == "team":
        ok = isinstance(value, str) and bool(value.strip())
        return FieldCheck(ok=ok, value=value if ok else None, errors=[] if ok else ["team is a team's name."])
    return FieldCheck(ok=False, value=None, errors=[f"{field} is not a field of a ticket."])


def validate_values(values: dict[str, Value]) -> Validation:
    fields = {field: check_value(field, value) for field, value in values.items()}
    return Validation(ok=all(f.ok for f in fields.values()), fields=fields)


def suggest_values(ticket_id: str, values: dict[str, Value]) -> SuggestResult:
    """The one write path: values land as suggestions for a person to approve, never approved."""
    ticket = get_ticket(ticket_id)
    written, skipped = [], []
    for field, value in values.items():
        check = check_value(field, value)
        if field not in ticket.fields:
            skipped.append(Skipped(field=field, reason="unknown_field", detail=check.errors[0]))
        elif (ticket.ticket_id, field) in APPROVED:
            skipped.append(Skipped(field=field, reason="approved", detail=f"{field} is approved; a person changes it."))
        elif not check.ok:
            skipped.append(Skipped(field=field, reason="invalid_value", detail=check.errors[0]))
        else:
            ticket.fields[field] = check.value
            written.append(field)
    return SuggestResult(ticket_id=ticket.ticket_id, written=written, skipped=skipped)


# --------------------------------------------------------------------------- MCP layer

P = ParamSpec("P")
R = TypeVar("R")


def domain_errors(tool: Callable[P, R]) -> Callable[P, R]:
    """Maps domain exceptions to `ToolError` once, for every tool. The agent reads the message
    as an `isError` result, so it says what was wrong and what to do next. FastMCP 4 hands
    middleware the exception already masked, which is why this is a decorator."""

    @functools.wraps(tool)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return tool(*args, **kwargs)
        except NotFound as error:
            raise ToolError(f"{error} Find the ticket number with find_tickets.") from error

    return wrapper


mcp = FastMCP(
    "tickets",
    instructions="Read support tickets and suggest their category, priority and team. Suggestions wait for a person to approve them.",
    # Any exception other than ToolError reaches the agent as "Error calling tool ...", no internals.
    mask_error_details=True,
)

READ = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

TicketId = Annotated[str, Field(description="Ticket number, e.g. '000042' or '42'.")]
Values = Annotated[
    dict[str, Value],
    Field(description="Values keyed by field (category, priority, team), e.g. {\"category\": \"access\", \"priority\": 2}."),
]


# Sync tools: FastMCP runs them in a thread pool, so blocking database work never stalls the event loop.
@mcp.tool(title="Get ticket", annotations=READ)
@domain_errors
def get_ticket_details(ticket_id: TicketId) -> Ticket:
    """One ticket with its title and fields.

    Use it to read a ticket before suggesting values for it. To find a ticket by its title, use
    find_tickets instead. Returns the ticket number, the title, and category, priority and team;
    a field with no value yet is null.
    """
    return get_ticket(ticket_id)


@mcp.tool(
    title="Find tickets",
    annotations=READ,
    description=(
        f"Tickets whose title contains the query, at most {MAX_RESULTS} per page. Use it to find a "
        "ticket number; to read one ticket, use get_ticket_details. Returns `tickets`, `next_cursor` "
        "for the next page, and a `note` when more tickets match than one page holds."
    ),
)
@domain_errors
def find_tickets(
    query: Annotated[str, Field(description="Part of the ticket title, e.g. 'login'.", min_length=2)],
    cursor: Annotated[str | None, Field(description="next_cursor of the previous page; omit for the first page.")] = None,
) -> TicketPage:
    return search_tickets(query, MAX_RESULTS, cursor)


@mcp.tool(title="Validate ticket fields", annotations=READ)
@domain_errors
def validate_ticket_fields(values: Values) -> Validation:
    """Checks values the way suggest_ticket_fields would store them, without writing anything.

    Use it on values you are about to suggest. Returns `ok` and, per field, the value as the
    ticket system stores it or one sentence per error.
    """
    return validate_values(values)


@mcp.tool(
    title="Suggest ticket fields",
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
)
@domain_errors
def suggest_ticket_fields(ticket_id: TicketId, values: Values) -> SuggestResult:
    """Writes values into a ticket as suggestions for a person to approve.

    Fields already approved are not overwritten. Returns `written`, the fields that now hold
    your value, and `skipped`, each other field with a reason: unknown_field, approved or
    invalid_value. Check values with validate_ticket_fields first.
    """
    return suggest_values(ticket_id, values)


# --------------------------------------------------------------------------- REST layer and app

# stateless_http: any replica answers any call, and LangChain's client opens a session per call anyway.
mcp_app = mcp.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load heavy resources (pools, embedding models) here, not on the first call.
    async with mcp_app.lifespan(app):  # without this the MCP session manager never starts
        yield


app = FastAPI(title="Tickets", lifespan=lifespan)
app.mount("/mcp", mcp_app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/tickets/{ticket_id}")
def read_ticket(ticket_id: str) -> Ticket:
    try:
        return get_ticket(ticket_id)
    except NotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
