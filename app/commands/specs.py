import json
from pathlib import Path

import click

from app.spec_sync import (
    DEFAULT_SPEC_ALLOWLIST,
    SpecSyncService,
)


@click.group()
def specs():
    """BIP/BOLT specification sync commands."""


@specs.command()
@click.argument("spec_ids", nargs=-1)
@click.option(
    "--local-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Read spec files from a local directory instead of GitHub.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Write normalized raw spec JSON records to this directory.",
)
def sync(spec_ids, local_dir, output_dir):
    """Sync BIP/BOLT raw specs.

    With no SPEC_IDS, the MVP allowlist is synced:
    BIP-32, BIP-174, BIP-340, BIP-341, BIP-342, BOLT-11, and BOLT-12.
    """
    service = SpecSyncService()

    if local_dir:
        raw_specs = service.sync_local_directory(local_dir)
    else:
        requested_specs = (
            [service.parse_spec_ref(value) for value in spec_ids]
            if spec_ids
            else DEFAULT_SPEC_ALLOWLIST
        )
        unknown_specs = [
            value
            for value, spec_ref in zip(spec_ids, requested_specs)
            if spec_ref is None
        ]
        if unknown_specs:
            raise click.ClickException(
                f"Could not parse spec id(s): {', '.join(unknown_specs)}"
            )
        raw_specs = service.sync_allowlist(requested_specs)

    records = [spec.to_dict() for spec in raw_specs]
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        for record in records:
            filename = f"{record['spec_id'].lower()}.json"
            (output_dir / filename).write_text(
                json.dumps(record, indent=2), encoding="utf-8"
            )

    click.echo(json.dumps(records, indent=2))


commands = specs
