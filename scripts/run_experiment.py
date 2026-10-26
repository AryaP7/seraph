#!/usr/bin/env python
"""Run the FR35 ablation under a committed pre-registration (T10).

    python scripts/run_experiment.py --status
    python scripts/run_experiment.py --dataset fixture --out runs/exp-01.json
    python scripts/run_experiment.py --dataset fixture --transfer JSE
    python scripts/run_experiment.py --show runs/exp-01.json

**This script cannot commit the pre-registration**, and that is deliberate.
DR-05 step 5 left it to the owner, for the reason pre-registration exists:
a design is fixed by a person before any result is seen, and a script writing
`preregistration.json` as part of a build step would defeat the whole
mechanism. `--status` prints the one command to run, once, when ready.

The only dataset wired in is `fixture`, the synthetic one T10's acceptance
asks for: "A small supplied valid dataset exercises runner/configuration/
report plumbing; full expensive scientific evaluation is separate." A real
run needs reconciled states per labelled epoch from the archive, which this
installation does not hold for all six epochs — `--status` says so rather
than letting `--dataset real` look available.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from seraph.validation import experiment, experiment_store  # noqa: E402
from seraph.validation.preregistration import DEFAULT_PATH, verify  # noqa: E402

COMMIT_HINT = (
    'python -c "from seraph.validation.preregistration import commit; '
    'print(commit())"')


def status(design_path: Path) -> int:
    print("PRE-REGISTRATION")
    if not design_path.exists():
        print(f"  [absent] {design_path}")
        print("  D5(d) gates every AUC on a committed design. DR-05 step 5")
        print("  left this to the owner on purpose. When ready, once:")
        print(f"    {COMMIT_HINT}")
        print("  commit() refuses to overwrite, so it cannot be run twice by")
        print("  accident.")
    else:
        intact, digest = verify(design_path)
        mark = "ok" if intact else "HASH MISMATCH"
        print(f"  [{mark}] {design_path}  {digest[:16]}")
        if not intact:
            print("  The file no longer matches its own recorded hash, so no")
            print("  result produced under it is reportable.")

    print()
    print("DATASETS")
    print("  fixture   available -- synthetic, labelled as such, for plumbing")
    print("  stored    available -- explicit --run-ids, --epochs and --cutoff")
    print("            --validate-inputs reports real coverage without calibration")
    print()
    print("SCOPE")
    print("  Tables A (4 folds) / B (2) / C (6) answer three different")
    print("  questions and are never ranked together.")
    print("  Measured Table C rows serialize through the published contract.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true",
                        help="what is committed and what is runnable")
    parser.add_argument("--show", type=Path,
                        help="render a saved report artefact")
    parser.add_argument("--dataset", choices=("fixture", "stored"),
                        help="which labelled dataset to run")
    parser.add_argument("--store", type=Path, default=ROOT/'prototype_runs/seraph.sqlite')
    parser.add_argument("--run-ids", nargs='+')
    parser.add_argument("--epochs", type=Path, help='Explicit epoch windows and observed session axes as JSON')
    parser.add_argument("--cutoff", help='Offset-aware evaluation cutoff')
    parser.add_argument("--validate-inputs", action='store_true')
    parser.add_argument("--derive-forward-fill", action='store_true',
                        help='Compute the missing C8 mode from the selected actual pillar input run')
    parser.add_argument("--preregistration", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--tables", default="A,B,C")
    parser.add_argument("--per-epoch", type=int, default=24,
                        help="fixture observations per epoch")
    parser.add_argument("--out", type=Path,
                        help="write the report artefact here")
    parser.add_argument("--transfer", metavar="MARKET",
                        help="also run the FR37 fixed-weight transfer test")
    args = parser.parse_args(argv)

    if args.show:
        report, digest, intact = experiment_store.load(args.show)
        print(f"artefact {digest[:16]}  "
              f"{'intact' if intact else 'EDITED AFTER WRITING'}")
        if not intact:
            print("Do not quote these numbers: the file does not match its "
                  "own hash.")
        print()
        print(experiment_store.render(report))
        return 0 if intact else 1

    if args.status or not args.dataset:
        return status(args.preregistration)

    provenance = {}
    if args.dataset == 'stored':
        if not all((args.run_ids, args.epochs, args.cutoff)):
            parser.error('stored dataset requires --run-ids, --epochs and --cutoff')
        from seraph.orchestration.run_store import RunStore
        from seraph.validation.datasets import from_run_store, derive_reconciliation
        stored = RunStore(args.store)
        if args.derive_forward_fill:
            if len(args.run_ids) != 1:
                parser.error('Select one source run when deriving forward-fill')
            derived = derive_reconciliation(stored, args.run_ids[0],
                                            mode='forward_fill', cutoff=args.cutoff)
            args.run_ids.append(derived)
        adapted = from_run_store(
            stored, args.run_ids,
            json.loads(args.epochs.read_text(encoding='utf-8')), cutoff=args.cutoff)
        dataset = adapted['dataset']
        provenance = adapted['provenance_manifest']
        print(json.dumps(adapted['coverage_report'], indent=2))
        if args.validate_inputs:
            return 0
        if args.transfer:
            parser.error('stored transfer requires a separate declared market dataset')
    else:
        from fixtures import experiment_dataset
        dataset = experiment_dataset.build(per_epoch=args.per_epoch)
        print(f"dataset: fixture, {len(dataset)} epochs, synthetic")
        print(f"         {experiment_dataset.PROVENANCE}")
    print()

    result = experiment.run(
        dataset=dataset, preregistration=args.preregistration,
        tables=tuple(t.strip() for t in args.tables.split(",") if t.strip()))
    if result.status == "error":
        print(f"REFUSED [{result.error.kind}] {result.error.field}")
        print(f"  {result.error.detail}")
        return 2

    report = result.value.model_copy(update={'dataset_provenance': provenance})
    print(experiment_store.render(report))

    if args.out:
        try:
            path, digest = experiment_store.save(report, args.out)
        except FileExistsError as exc:
            print(f"\nnot written: {exc}")
            return 2
        print(f"\nartefact {digest[:16]} -> {path}")

    if args.transfer:
        print()
        print(_transfer(report, dataset, args.transfer))
    return 0


def _transfer(report, dataset, market: str) -> str:
    """FR37: the same weights, a different market, no refit.

    The weights come from a measured Table B row, so the artefact being
    transferred is one this run actually produced rather than a fresh fit --
    O9's acceptance asks for bit-identical weight vectors between the two
    runs, which is only checkable if both sides name the same artefact.
    """
    from seraph.validation import transfer as transfer_mod

    # There is no second-market corpus in this installation, so one of the
    # fixture's epochs stands in for the target market -- which makes this a
    # plumbing check, and the result says so.
    #
    # The donor must therefore be a row that did NOT train on the stand-in
    # epoch, or the "out-of-sample" AUC is in-sample. Under leave-one-epoch-out
    # the row HELD OUT at STAND_IN is exactly the one fitted without it.
    stand_in = "taper_2013"
    donor = next((r for r in report.measured()
                  if r.table == "B" and len(r.pillar_subset) > 1
                  and r.epoch == stand_in
                  and stand_in not in r.train_epochs), None)
    if donor is None:
        return (f"FR37 transfer: skipped, this run measured no multi-pillar "
                f"Table B row held out at {stand_in}, so every available "
                f"artefact was fitted on the stand-in target and the AUC "
                f"would be in-sample.")

    target = dataset[stand_in].observations["kalman"]
    weights = report.weight_artefacts.get(donor.weights_artefact_id)
    if weights is None:
        return (f"FR37 transfer: skipped, the artefact "
                f"{donor.weights_artefact_id[:12]} was not retained by "
                f"this run. Refitting it here would make this not a "
                f"fixed-weight transfer, so the test is skipped instead.")

    # No NSE reference is passed, so no degradation is reported. The stand-in
    # target IS an NSE fixture epoch, so the only reference available is the
    # donor row's own AUC -- which was measured on this very sample with these
    # very weights. Passing it produced a degradation of exactly +0.0000,
    # which looks like perfect transfer and is really the same number twice.
    # A genuine reference needs a real second market.
    outcome = transfer_mod.transfer(
        weights=weights, target_market=market, observations=target,
        target_epochs=(stand_in,), amber_threshold=0.5)
    if outcome.status == "error":
        return (f"FR37 transfer REFUSED [{outcome.error.field}]\n  "
                f"{outcome.error.detail}")
    value = outcome.value
    return "\n".join([
        f"FR37 TRANSFER  NSE -> {value.target_market}",
        f"  subset            {'+'.join(value.pillar_subset)}",
        f"  refit             {value.refit}",
        f"  artefact          {value.weights_artefact_id[:16]} "
        f"(calibrated on {', '.join(value.calibrated_on_epochs)})",
        f"  out-of-sample AUC {value.out_of_sample_auc:.4f} "
        f"on {value.observations} observations",
        "  NSE reference     none, so no degradation is reported",
        f"  {value.bound_note}",
        f"  scope: {value.scope_reason}",
        f"  NOTE: the target observations are the fixture's {stand_in} epoch,",
        "  not a second market's. This exercises the transfer path and is NOT",
        "  an O9 result: a real one needs one of IDX/Ibovespa/JSE via",
        "  yfinance, which SPEC O9 says is free and is not wired up here.",
    ])



if __name__ == "__main__":
    raise SystemExit(main())
