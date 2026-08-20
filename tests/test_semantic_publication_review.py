from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from subdomains.ttrpg.semantic_publication_review import (
    AcceptedSemanticPublicationReviewCensus,
    ItemReviewRef,
    ReviewedCapability,
    ReviewedOpaqueAsset,
    ReviewedProviderCarrierRelationship,
    ReviewedSourceEvidence,
    SemanticPublicationReview,
    SemanticPublicationReviewError,
    collect_accepted_semantic_publication_reviews,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def asset(
    asset_id: str = "pf2er.asset:training-token",
    *,
    body_label: str = "training-token-body",
) -> ReviewedOpaqueAsset:
    return ReviewedOpaqueAsset(
        asset_id,
        digest(body_label),
        digest(f"binding:{body_label}"),
    )


def relationship(
    carrier_id: str = "pf2er:training-creature",
) -> ReviewedProviderCarrierRelationship:
    return ReviewedProviderCarrierRelationship(
        "pf2er.relationship:training-tool-carrier",
        "pf2er:training-tool",
        carrier_id,
    )


def review(
    entity_id: str = "pf2er:training-creature",
    *,
    entity_kind: str = "ttrpg:creature",
    review_id: str | None = None,
    lifecycle_path: str | None = None,
    book_id: str = "paizo:synthetic-creature-book",
    book_digest: str | None = None,
    source_id: str = "synthetic-creatures",
    locator: str = "1.1",
    authority_digest: str | None = None,
    source_receipt_digest: str | None = None,
    source_evidence: tuple[ReviewedSourceEvidence, ...] | None = None,
    evidence_record_digest: str | None = None,
    semantic_receipt_digest: str | None = None,
    package_id: str = "ttrpg:synthetic-creature-package",
    semantic_generation_digest: str | None = None,
    with_lifecycle: bool = True,
    item_refs: tuple[ItemReviewRef, ...] = (),
    assets: tuple[ReviewedOpaqueAsset, ...] = (),
    relationships: tuple[ReviewedProviderCarrierRelationship, ...] = (),
) -> SemanticPublicationReview:
    slug = entity_id.split(":", 1)[1]
    return SemanticPublicationReview.build(
        review_id=review_id or f"ttrpg.review:{slug}",
        lifecycle_record_path=(
            None
            if not with_lifecycle
            else (
                lifecycle_path
                or "subdomains/ttrpg/AGENTS/synthetic-status/"
                f"{source_id}__{locator}.status.json"
            )
        ),
        lifecycle_record_digest=(
            digest(f"lifecycle:{entity_id}") if with_lifecycle else None
        ),
        ruleset_digest=digest("pf2er-ruleset"),
        entity_id=entity_id,
        entity_kind=entity_kind,
        book_id=book_id,
        book_digest=book_digest or digest(f"book:{book_id}"),
        source_id=source_id,
        source_evidence=(
            source_evidence
            if source_evidence is not None
            else (
                ReviewedSourceEvidence(
                    source_id,
                    locator,
                    source_receipt_digest
                    or digest(f"source-receipt:{entity_id}"),
                ),
            )
        ),
        source_generation=digest("source-generation"),
        authority_digest=authority_digest or digest("source-authority"),
        package_id=package_id,
        package_version="1.0.0",
        semantic_generation="ttrpg:synthetic-semantic-generation",
        semantic_generation_digest=(
            semantic_generation_digest or digest(f"generation:{package_id}")
        ),
        compiler_id="ttrpg:pf2er-semantic-compiler",
        compiler_version="1.0.0",
        compiler_digest=digest("semantic-compiler"),
        projection_id=(
            "ttrpg:pf2er-item-definition"
            if entity_kind == "ttrpg:item"
            else "ttrpg:pf2er-creature-definition"
        ),
        projection_version="1.0.0",
        projection_digest=digest(f"projection:{entity_kind}"),
        raw_definition_digest=digest(f"raw:{entity_id}"),
        projected_definition_digest=digest(f"projected:{entity_id}"),
        evidence_authority_id="ttrpg:pf2er-semantic-evidence",
        evidence_record_digest=(
            evidence_record_digest or digest(f"evidence:{entity_id}")
        ),
        semantic_receipt_digest=(
            semantic_receipt_digest or digest(f"semantic-receipt:{entity_id}")
        ),
        required_capabilities=(
            ReviewedCapability("pf2er.runtime:training-action", "1.0.0"),
            ReviewedCapability("pf2er.runtime:action-economy", "1.0.0"),
        ),
        item_review_refs=item_refs,
        opaque_assets=assets,
        provider_carrier_relationships=relationships,
        accepted_deferrals=(
            "synthetic:social-behavior",
            "synthetic:noncombat-description",
        ),
        reviewer_role="ttrpg:semantic-publication-reviewer",
        reviewed_on="2026-08-13",
        review_scope="ttrpg:pf2er-offline-provisioning",
    )


def item_review(*, assets: tuple[ReviewedOpaqueAsset, ...] = ()) -> SemanticPublicationReview:
    return review(
        "pf2er:training-tool",
        entity_kind="ttrpg:item",
        book_id="paizo:synthetic-equipment-book",
        source_id="synthetic-equipment",
        locator="2.1",
        package_id="ttrpg:synthetic-equipment-package",
        assets=assets,
        with_lifecycle=False,
    )


class SemanticPublicationReviewTests(unittest.TestCase):
    def test_record_is_factory_only_canonical_and_round_trips(self) -> None:
        with self.assertRaisesRegex(TypeError, "built through build"):
            SemanticPublicationReview()

        opaque_asset = asset()
        relation = relationship()
        first = review(
            assets=(opaque_asset,),
            relationships=(relation,),
        )
        second = SemanticPublicationReview.from_json(first.canonical_json())

        self.assertEqual(first, second)
        self.assertEqual(
            first.to_dict()["kind"],
            "pf2er-semantic-publication-review",
        )
        self.assertEqual(first.to_dict()["decision"], "accepted")
        self.assertEqual(
            first.to_dict()["lifecycleRecord"],
            {
                "path": (
                    "subdomains/ttrpg/AGENTS/synthetic-status/"
                    "synthetic-creatures__1.1.status.json"
                ),
                "sha256": digest("lifecycle:pf2er:training-creature"),
            },
        )
        self.assertEqual(
            first.to_dict()["entity"]["projectedDefinitionDigest"],
            digest("projected:pf2er:training-creature"),
        )
        self.assertEqual(
            first.to_dict()["opaqueAssets"][0][
                "privateAcquisitionBindingDigest"
            ],
            digest("binding:training-token-body"),
        )
        self.assertEqual(
            first.required_capabilities,
            tuple(sorted(first.required_capabilities)),
        )
        self.assertEqual(
            first.accepted_deferrals,
            tuple(sorted(first.accepted_deferrals)),
        )
        self.assertEqual(
            json.loads(first.canonical_json()),
            first.to_dict(),
        )

        item = item_review()
        self.assertIsNone(item.to_dict()["lifecycleRecord"])
        self.assertEqual(item.entity_kind, "ttrpg:item")

    def test_spell_and_creature_ability_are_canonical_non_creature_reviews(self) -> None:
        for entity_kind, entity_id in (
            ("ttrpg:spell", "pf2er:summon-instrument"),
            ("ttrpg:creature-ability", "pf2er:slink"),
        ):
            with self.subTest(entity_kind=entity_kind):
                original = review(
                    entity_id,
                    entity_kind=entity_kind,
                    with_lifecycle=False,
                )
                decoded = SemanticPublicationReview.from_json(
                    original.canonical_json()
                )

                self.assertEqual(decoded, original)
                self.assertEqual(decoded.entity_kind, entity_kind)
                self.assertIsNone(decoded.lifecycle_record_path)
                self.assertIsNone(decoded.to_dict()["lifecycleRecord"])

        with self.assertRaisesRegex(
            SemanticPublicationReviewError,
            "non-creature review lifecycleRecord must be null",
        ):
            review("pf2er:slink", entity_kind="ttrpg:creature-ability")

        with self.assertRaisesRegex(
            SemanticPublicationReviewError,
            "entityKind must be",
        ):
            review(
                "pf2er:unsupported-feat",
                entity_kind="ttrpg:feat",
                with_lifecycle=False,
            )

    def test_schema_digest_and_json_duplicate_fences_fail_closed(self) -> None:
        original = review()
        tampered = deepcopy(original.to_dict())
        tampered["entity"]["projectedDefinitionDigest"] = digest("forged")
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "review digest mismatch"
        ):
            SemanticPublicationReview.from_dict(tampered)

        extra = deepcopy(original.to_dict())
        extra["approvalToken"] = "not-part-of-this-contract"
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "must have exactly"
        ):
            SemanticPublicationReview.from_dict(extra)

        rejected = deepcopy(original.to_dict())
        rejected["decision"] = "rejected"
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "identity is unsupported"
        ):
            SemanticPublicationReview.from_dict(rejected)

        boolean_schema = deepcopy(original.to_dict())
        boolean_schema["schema"] = True
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "identity is unsupported"
        ):
            SemanticPublicationReview.from_dict(boolean_schema)

        duplicated = original.canonical_json().decode("utf-8").replace(
            '"schema":2', '"schema":2,"schema":2', 1
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "duplicate key: schema"
        ):
            SemanticPublicationReview.from_json(duplicated)

    def test_private_path_date_and_exact_nested_shapes_are_strict(self) -> None:
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "TTRPG repo-relative"
        ):
            review(lifecycle_path="../outside.status.json")

        packet = review().to_dict()
        packet["reviewer"]["reviewedOn"] = "2026-02-30"
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "calendar date"
        ):
            SemanticPublicationReview.from_dict(packet)

        packet = review().to_dict()
        packet["projection"]["sourcePath"] = "private/acquisition/path"
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "projection must have exactly"
        ):
            SemanticPublicationReview.from_dict(packet)

        packet = review().to_dict()
        packet["lifecycleRecord"] = None
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "creature review requires"
        ):
            SemanticPublicationReview.from_dict(packet)

    def test_complete_accepted_census_is_deterministic_and_lookup_ready(self) -> None:
        shared_asset = asset()
        shared_relationship = relationship()
        item = item_review(assets=(shared_asset,))
        creature = review(
            item_refs=(
                ItemReviewRef(item.entity_id, item.review_id, item.review_digest),
            ),
            assets=(shared_asset,),
            relationships=(shared_relationship,),
        )

        forward = collect_accepted_semantic_publication_reviews((item, creature))
        reverse = AcceptedSemanticPublicationReviewCensus.build((creature, item))

        self.assertEqual(forward.canonical_json(), reverse.canonical_json())
        self.assertEqual(
            forward.entity_ids,
            ("pf2er:training-creature", "pf2er:training-tool"),
        )
        self.assertIs(forward.review(creature.entity_id), creature)
        self.assertIs(forward.review_id(item.review_id), item)
        self.assertEqual(forward.assets, (shared_asset,))
        self.assertEqual(forward.relationships, (shared_relationship,))
        self.assertEqual(
            json.loads(forward.canonical_json())["censusDigest"],
            forward.census_digest,
        )
        decoded = AcceptedSemanticPublicationReviewCensus.from_json(
            forward.canonical_json()
        )
        self.assertEqual(decoded.canonical_json(), forward.canonical_json())
        self.assertEqual(
            decoded.review(creature.entity_id).review_digest,
            creature.review_digest,
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "census digest mismatch"
        ):
            AcceptedSemanticPublicationReviewCensus.build(
                (item, creature),
                expected_census_digest=digest("wrong-census"),
            )

    def test_census_decoders_reject_tamper_extra_duplicate_and_nonfinite(self) -> None:
        item = item_review()
        creature = review(
            item_refs=(
                ItemReviewRef(item.entity_id, item.review_id, item.review_digest),
            )
        )
        census = AcceptedSemanticPublicationReviewCensus.build((item, creature))

        tampered_review = deepcopy(census.to_dict())
        tampered_review["reviews"][0]["entity"][
            "projectedDefinitionDigest"
        ] = digest("tampered-projected-definition")
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "review digest mismatch"
        ):
            AcceptedSemanticPublicationReviewCensus.from_dict(tampered_review)

        tampered_census = deepcopy(census.to_dict())
        tampered_census["censusDigest"] = digest("tampered-census")
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "census digest mismatch"
        ):
            AcceptedSemanticPublicationReviewCensus.from_dict(tampered_census)

        extra = deepcopy(census.to_dict())
        extra["approvalPolicy"] = "not-part-of-this-contract"
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "must have exactly"
        ):
            AcceptedSemanticPublicationReviewCensus.from_dict(extra)

        unsupported = deepcopy(census.to_dict())
        unsupported["schema"] = True
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "identity is unsupported"
        ):
            AcceptedSemanticPublicationReviewCensus.from_dict(unsupported)

        canonical = census.canonical_json().decode("utf-8")
        duplicate = canonical.replace(
            '"censusDigest":', '"censusDigest":"duplicate","censusDigest":', 1
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "duplicate key: censusDigest"
        ):
            AcceptedSemanticPublicationReviewCensus.from_json(duplicate)

        prefix, suffix = canonical.rsplit('"schema":2', 1)
        nonfinite = prefix + '"schema":NaN' + suffix
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "non-finite number: NaN"
        ):
            AcceptedSemanticPublicationReviewCensus.from_json(nonfinite)

    def test_census_rejects_duplicate_record_id_entity_and_path(self) -> None:
        first = review()
        cases = {
            "review digests": first,
            "review IDs": review(
                "pf2er:second-creature",
                review_id=first.review_id,
                locator="1.2",
            ),
            "entity IDs": review(
                first.entity_id,
                review_id="ttrpg.review:alternate",
                locator="1.2",
            ),
            "lifecycle record paths": review(
                "pf2er:second-creature",
                lifecycle_path=first.lifecycle_record_path,
                locator="1.2",
            ),
            "evidence record digests": review(
                "pf2er:second-creature",
                evidence_record_digest=first.evidence_record_digest,
                locator="1.2",
            ),
            "semantic receipt digests": review(
                "pf2er:second-creature",
                semantic_receipt_digest=first.semantic_receipt_digest,
                locator="1.2",
            ),
        }
        for label, duplicate in cases.items():
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    SemanticPublicationReviewError,
                    f"duplicate {label}",
                ):
                    AcceptedSemanticPublicationReviewCensus.build(
                        (first, duplicate)
                    )

    def test_census_allows_distinct_entities_at_one_authenticated_locator(self) -> None:
        source_receipt = digest("source-receipt:core-mc1:316.2")
        viper = review(
            "pf2er:viper",
            book_id="paizo:monster-core-one",
            source_id="core-mc1",
            locator="316.2",
            package_id="ttrpg:monster-core-one",
            source_receipt_digest=source_receipt,
        )
        slink = review(
            "pf2er:slink",
            entity_kind="ttrpg:creature-ability",
            book_id=viper.book_id,
            book_digest=viper.book_digest,
            source_id=viper.source_id,
            locator=viper.source_evidence[0].locator,
            package_id=viper.package_id,
            semantic_generation_digest=viper.semantic_generation_digest,
            source_receipt_digest=source_receipt,
            with_lifecycle=False,
        )

        census = AcceptedSemanticPublicationReviewCensus.build((slink, viper))
        decoded = AcceptedSemanticPublicationReviewCensus.from_json(
            census.canonical_json()
        )

        self.assertEqual(decoded.canonical_json(), census.canonical_json())
        self.assertEqual(decoded.entity_ids, ("pf2er:slink", "pf2er:viper"))
        self.assertEqual(
            decoded.review("pf2er:slink").source_evidence,
            decoded.review("pf2er:viper").source_evidence,
        )
        self.assertNotEqual(
            decoded.review("pf2er:slink").evidence_record_digest,
            decoded.review("pf2er:viper").evidence_record_digest,
        )

        conflicting_receipt = review(
            "pf2er:slink",
            entity_kind="ttrpg:creature-ability",
            book_id=viper.book_id,
            book_digest=viper.book_digest,
            source_id=viper.source_id,
            locator=viper.source_evidence[0].locator,
            package_id=viper.package_id,
            semantic_generation_digest=viper.semantic_generation_digest,
            source_receipt_digest=digest("forged-source-receipt"),
            with_lifecycle=False,
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError,
            "authenticated source target fence",
        ):
            AcceptedSemanticPublicationReviewCensus.build(
                (viper, conflicting_receipt)
            )

        tampered = deepcopy(census.to_dict())
        tampered["reviews"][0]["entity"]["evidenceRecordDigest"] = digest(
            "forged-entity-evidence"
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError,
            "review digest mismatch",
        ):
            AcceptedSemanticPublicationReviewCensus.from_dict(tampered)

    def test_shared_root_keeps_distinct_refined_entity_evidence(self) -> None:
        root = digest("core-mc1:98.2:root")
        carrier_refinement = digest("core-mc1:98.2:hadrosaurid-carrier")
        ability_refinement = digest("core-mc1:98.2:trample-ability")
        common = {
            "book_id": "paizo:monster-core-one",
            "source_id": "core-mc1",
            "package_id": "ttrpg:pf2er-monster-core-one-hadrosaurid-trample",
        }
        hadrosaurid = review(
            "pf2er:hadrosaurid",
            source_evidence=(
                ReviewedSourceEvidence(
                    "core-mc1",
                    "98.2",
                    root,
                    (carrier_refinement,),
                ),
            ),
            **common,
        )
        trample = review(
            "pf2er:trample",
            entity_kind="ttrpg:creature-ability",
            book_digest=hadrosaurid.book_digest,
            semantic_generation_digest=(
                hadrosaurid.semantic_generation_digest
            ),
            source_evidence=(
                ReviewedSourceEvidence(
                    "core-mc1",
                    "98.2",
                    root,
                    (ability_refinement,),
                ),
            ),
            with_lifecycle=False,
            **common,
        )

        census = AcceptedSemanticPublicationReviewCensus.build(
            (hadrosaurid, trample)
        )
        decoded = AcceptedSemanticPublicationReviewCensus.from_json(
            census.canonical_json()
        )
        by_entity = {item.entity_id: item for item in decoded.reviews}
        self.assertEqual(
            by_entity["pf2er:hadrosaurid"].source_evidence[0]
            .source_receipt_digest,
            root,
        )
        self.assertEqual(
            by_entity["pf2er:hadrosaurid"].source_evidence[0]
            .refined_source_receipt_digests,
            (carrier_refinement,),
        )
        self.assertEqual(
            by_entity["pf2er:trample"].source_evidence[0]
            .refined_source_receipt_digests,
            (ability_refinement,),
        )
        self.assertIn(
            "refinedSourceReceiptDigests",
            by_entity["pf2er:trample"].to_dict()["entity"][
                "sourceEvidence"
            ][0],
        )

        conflicting_root = review(
            "pf2er:trample",
            entity_kind="ttrpg:creature-ability",
            book_digest=hadrosaurid.book_digest,
            semantic_generation_digest=(
                hadrosaurid.semantic_generation_digest
            ),
            source_evidence=(
                ReviewedSourceEvidence(
                    "core-mc1",
                    "98.2",
                    digest("forged-root"),
                    (ability_refinement,),
                ),
            ),
            with_lifecycle=False,
            **common,
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError,
            "authenticated source target fence",
        ):
            AcceptedSemanticPublicationReviewCensus.build(
                (hadrosaurid, conflicting_root)
            )

        with self.assertRaisesRegex(
            SemanticPublicationReviewError,
            "refinedSourceReceiptDigests contains duplicates",
        ):
            ReviewedSourceEvidence(
                "core-mc1",
                "98.2",
                root,
                (carrier_refinement, carrier_refinement),
            )

    def test_plural_source_evidence_is_sorted_and_exact(self) -> None:
        table = ReviewedSourceEvidence(
            "core-pc1",
            "287.5",
            digest("instrument-table"),
        )
        description = ReviewedSourceEvidence(
            "core-pc1",
            "290.1",
            digest("instrument-description"),
        )
        instrument = review(
            "pf2er:item.musical-instrument-handheld",
            entity_kind="ttrpg:item",
            book_id="paizo:player-core-one",
            source_id="core-pc1",
            package_id="ttrpg:pf2er-player-core-one",
            source_evidence=(description, table),
            with_lifecycle=False,
        )

        self.assertEqual(instrument.source_evidence, (table, description))
        self.assertEqual(
            instrument.to_dict()["entity"]["sourceEvidence"],
            [table.to_dict(), description.to_dict()],
        )
        decoded = SemanticPublicationReview.from_json(
            instrument.canonical_json()
        )
        self.assertEqual(decoded.source_evidence, (table, description))

        with self.assertRaisesRegex(
            SemanticPublicationReviewError,
            "sourceEvidence contains duplicates",
        ):
            review(
                "pf2er:item.musical-instrument-handheld",
                entity_kind="ttrpg:item",
                source_id="core-pc1",
                source_evidence=(table, table),
                with_lifecycle=False,
            )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError,
            "reviewed publication source",
        ):
            review(
                "pf2er:item.musical-instrument-handheld",
                entity_kind="ttrpg:item",
                source_id="core-pc1",
                source_evidence=(
                    ReviewedSourceEvidence(
                        "core-mc1",
                        "287.5",
                        digest("instrument-table"),
                    ),
                ),
                with_lifecycle=False,
            )

    def test_census_requires_exact_item_review_resolution(self) -> None:
        item = item_review()
        absent = review(
            item_refs=(
                ItemReviewRef(item.entity_id, item.review_id, item.review_digest),
            )
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "absent from the accepted census"
        ):
            AcceptedSemanticPublicationReviewCensus.build((absent,))

        mismatched = review(
            item_refs=(
                ItemReviewRef(item.entity_id, item.review_id, digest("wrong-review")),
            )
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "conflicts with its accepted record"
        ):
            AcceptedSemanticPublicationReviewCensus.build((item, mismatched))

        non_item = review(
            "pf2er:other-creature",
            review_id="ttrpg.review:other-creature",
            locator="1.2",
        )
        wrong_kind_ref = review(
            item_refs=(
                ItemReviewRef(
                    non_item.entity_id,
                    non_item.review_id,
                    non_item.review_digest,
                ),
            )
        )
        with self.assertRaisesRegex(
            SemanticPublicationReviewError, "conflicts with its accepted record"
        ):
            AcceptedSemanticPublicationReviewCensus.build(
                (non_item, wrong_kind_ref)
            )

    def test_census_rejects_cross_record_authority_conflicts(self) -> None:
        first_asset = asset()
        first = review(assets=(first_asset,), relationships=(relationship(),))

        conflict_cases = (
            (
                review(
                    "pf2er:second-creature",
                    locator="1.2",
                    authority_digest=digest("another-authority"),
                ),
                "source authority fence",
            ),
            (
                review(
                    "pf2er:second-creature",
                    locator="1.2",
                    assets=(asset(body_label="different-body"),),
                ),
                "opaque asset binding",
            ),
            (
                review(
                    "pf2er:second-creature",
                    locator="1.2",
                    relationships=(relationship("pf2er:second-creature"),),
                ),
                "provider/carrier relationship",
            ),
            (
                review(
                    "pf2er:second-creature",
                    book_id="paizo:other-synthetic-book",
                    source_id="other-synthetic-source",
                    locator="3.1",
                    package_id=first.package_id,
                    semantic_generation_digest=first.semantic_generation_digest,
                ),
                "semantic package fence",
            ),
        )
        for conflicting, message in conflict_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(
                    SemanticPublicationReviewError, message
                ):
                    AcceptedSemanticPublicationReviewCensus.build(
                        (first, conflicting)
                    )


if __name__ == "__main__":
    unittest.main()
