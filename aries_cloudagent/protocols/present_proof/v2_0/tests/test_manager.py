import json

from time import time

from asynctest import TestCase as AsyncTestCase
from asynctest import mock as async_mock

from .....core.in_memory import InMemoryProfile
from .....indy.holder import IndyHolder
from .....indy.sdk.holder import IndySdkHolder
from .....indy.issuer import IndyIssuer
from .....ledger.base import BaseLedger
from .....messaging.decorators.attach_decorator import AttachDecorator
from .....messaging.request_context import RequestContext
from .....messaging.responder import BaseResponder, MockResponder
from .....storage.error import StorageNotFoundError
from .....indy.verifier import IndyVerifier
from .....indy.sdk.verifier import IndySdkVerifier

from ....didcomm_prefix import DIDCommPrefix

from ...indy.xform import indy_proof_req_preview2indy_requested_creds
from ...indy.pres_preview import IndyPresAttrSpec, IndyPresPreview, IndyPresPredSpec

from .. import manager as test_module
from ..manager import V20PresManager, V20PresManagerError
from ..messages.pres import V20Pres
from ..messages.pres_ack import V20PresAck
from ..messages.pres_format import V20PresFormat
from ..messages.pres_proposal import V20PresProposal
from ..messages.pres_request import V20PresRequest
from ..models.pres_exchange import V20PresExRecord


CONN_ID = "connection_id"
ISSUER_DID = "NcYxiDXkpYi6ov5FcYDi1e"
S_ID = f"{ISSUER_DID}:2:vidya:1.0"
CD_ID = f"{ISSUER_DID}:3:CL:{S_ID}:tag1"
RR_ID = f"{ISSUER_DID}:4:{CD_ID}:CL_ACCUM:0"
PRES_PREVIEW = IndyPresPreview(
    attributes=[
        IndyPresAttrSpec(name="player", cred_def_id=CD_ID, value="Richie Knucklez"),
        IndyPresAttrSpec(
            name="screenCapture",
            cred_def_id=CD_ID,
            mime_type="image/png",
            value="aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
        ),
    ],
    predicates=[
        IndyPresPredSpec(
            name="highScore", cred_def_id=CD_ID, predicate=">=", threshold=1000000
        )
    ],
)
PRES_PREVIEW_NAMES = IndyPresPreview(
    attributes=[
        IndyPresAttrSpec(
            name="player", cred_def_id=CD_ID, value="Richie Knucklez", referent="0"
        ),
        IndyPresAttrSpec(
            name="screenCapture",
            cred_def_id=CD_ID,
            mime_type="image/png",
            value="aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
            referent="0",
        ),
    ],
    predicates=[
        IndyPresPredSpec(
            name="highScore", cred_def_id=CD_ID, predicate=">=", threshold=1000000
        )
    ],
)
PROOF_REQ_NAME = "name"
PROOF_REQ_VERSION = "1.0"
PROOF_REQ_NONCE = "12345"

NOW = int(time())


class TestV20PresManager(AsyncTestCase):
    async def setUp(self):
        self.profile = InMemoryProfile.test_profile()
        injector = self.profile.context.injector

        Ledger = async_mock.MagicMock(BaseLedger, autospec=True)
        self.ledger = Ledger()
        self.ledger.get_schema = async_mock.CoroutineMock(
            return_value=async_mock.MagicMock()
        )
        self.ledger.get_credential_definition = async_mock.CoroutineMock(
            return_value={"value": {"revocation": {"...": "..."}}}
        )
        self.ledger.get_revoc_reg_def = async_mock.CoroutineMock(
            return_value={
                "ver": "1.0",
                "id": RR_ID,
                "revocDefType": "CL_ACCUM",
                "tag": RR_ID.split(":")[-1],
                "credDefId": CD_ID,
                "value": {
                    "IssuanceType": "ISSUANCE_BY_DEFAULT",
                    "maxCredNum": 1000,
                    "publicKeys": {"accumKey": {"z": "1 ..."}},
                    "tailsHash": "3MLjUFQz9x9n5u9rFu8Ba9C5bo4HNFjkPNc54jZPSNaZ",
                    "tailsLocation": "http://sample.ca/path",
                },
            }
        )
        self.ledger.get_revoc_reg_delta = async_mock.CoroutineMock(
            return_value=(
                {
                    "ver": "1.0",
                    "value": {"prevAccum": "1 ...", "accum": "21 ...", "issued": [1]},
                },
                NOW,
            )
        )
        self.ledger.get_revoc_reg_entry = async_mock.CoroutineMock(
            return_value=(
                {
                    "ver": "1.0",
                    "value": {"prevAccum": "1 ...", "accum": "21 ...", "issued": [1]},
                },
                NOW,
            )
        )
        injector.bind_instance(BaseLedger, self.ledger)

        Holder = async_mock.MagicMock(IndyHolder, autospec=True)
        self.holder = Holder()
        get_creds = async_mock.CoroutineMock(
            return_value=(
                {
                    "cred_info": {
                        "referent": "dummy_reft",
                        "attrs": {
                            "player": "Richie Knucklez",
                            "screenCapture": "aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
                            "highScore": "1234560",
                        },
                    }
                },  # leave this comma: return a tuple
            )
        )
        self.holder.get_credentials_for_presentation_request_by_referent = get_creds
        self.holder.get_credential = async_mock.CoroutineMock(
            return_value=json.dumps(
                {
                    "schema_id": S_ID,
                    "cred_def_id": CD_ID,
                    "rev_reg_id": RR_ID,
                    "cred_rev_id": 1,
                }
            )
        )
        self.holder.create_presentation = async_mock.CoroutineMock(return_value="{}")
        self.holder.create_revocation_state = async_mock.CoroutineMock(
            return_value=json.dumps(
                {
                    "witness": {"omega": "1 ..."},
                    "rev_reg": {"accum": "21 ..."},
                    "timestamp": NOW,
                }
            )
        )
        injector.bind_instance(IndyHolder, self.holder)

        Verifier = async_mock.MagicMock(IndyVerifier, autospec=True)
        self.verifier = Verifier()
        self.verifier.verify_presentation = async_mock.CoroutineMock(
            return_value="true"
        )
        injector.bind_instance(IndyVerifier, self.verifier)

        self.manager = V20PresManager(self.profile)

    async def test_record_eq(self):
        same = [
            V20PresExRecord(
                pres_ex_id="dummy-0",
                thread_id="thread-0",
                role=V20PresExRecord.ROLE_PROVER,
            )
        ] * 2
        diff = [
            V20PresExRecord(
                pres_ex_id="dummy-1",
                role=V20PresExRecord.ROLE_PROVER,
            ),
            V20PresExRecord(
                pres_ex_id="dummy-0",
                thread_id="thread-1",
                role=V20PresExRecord.ROLE_PROVER,
            ),
            V20PresExRecord(
                pres_ex_id="dummy-1",
                thread_id="thread-0",
                role=V20PresExRecord.ROLE_VERIFIER,
            ),
        ]

        for i in range(len(same) - 1):
            for j in range(i, len(same)):
                assert same[i] == same[j]

        for i in range(len(diff) - 1):
            for j in range(i, len(diff)):
                assert diff[i] == diff[j] if i == j else diff[i] != diff[j]

    async def test_create_exchange_for_proposal(self):
        proposal = V20PresProposal()

        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            V20PresProposal, "serialize", autospec=True
        ):
            px_rec = await self.manager.create_exchange_for_proposal(
                CONN_ID, proposal, auto_present=None
            )
            save_ex.assert_called_once()

            assert px_rec.thread_id == proposal._thread_id
            assert px_rec.initiator == V20PresExRecord.INITIATOR_SELF
            assert px_rec.role == V20PresExRecord.ROLE_PROVER
            assert px_rec.state == V20PresExRecord.STATE_PROPOSAL_SENT

    async def test_receive_proposal(self):
        connection_record = async_mock.MagicMock(connection_id=CONN_ID)
        proposal = V20PresProposal()

        with async_mock.patch.object(V20PresExRecord, "save", autospec=True) as save_ex:
            px_rec = await self.manager.receive_pres_proposal(
                proposal,
                connection_record,
            )
            save_ex.assert_called_once()

            assert px_rec.state == V20PresExRecord.STATE_PROPOSAL_RECEIVED

    async def test_create_bound_request(self):
        comment = "comment"

        proposal = V20PresProposal(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            proposal_attach=[
                AttachDecorator.data_base64(PRES_PREVIEW.serialize(), ident="indy")
            ],
        )
        px_rec = V20PresExRecord(
            pres_proposal=proposal.serialize(),
            role=V20PresExRecord.ROLE_VERIFIER,
        )
        px_rec.save = async_mock.CoroutineMock()
        (ret_px_rec, pres_req_msg) = await self.manager.create_bound_request(
            pres_ex_record=px_rec,
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            comment=comment,
        )
        assert ret_px_rec is px_rec
        px_rec.save.assert_called_once()

    async def test_create_exchange_for_request(self):
        request = async_mock.MagicMock()
        request.indy_proof_request = async_mock.MagicMock()
        request._thread_id = "dummy"

        with async_mock.patch.object(V20PresExRecord, "save", autospec=True) as save_ex:
            px_rec = await self.manager.create_exchange_for_request(CONN_ID, request)
            save_ex.assert_called_once()

            assert px_rec.thread_id == request._thread_id
            assert px_rec.initiator == V20PresExRecord.INITIATOR_SELF
            assert px_rec.role == V20PresExRecord.ROLE_VERIFIER
            assert px_rec.state == V20PresExRecord.STATE_REQUEST_SENT

    async def test_receive_pres_request(self):
        px_rec_in = V20PresExRecord()

        with async_mock.patch.object(V20PresExRecord, "save", autospec=True) as save_ex:
            px_rec_out = await self.manager.receive_pres_request(px_rec_in)
            save_ex.assert_called_once()

            assert px_rec_out.state == V20PresExRecord.STATE_REQUEST_RECEIVED

    async def test_create_pres(self):
        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(pres_request=pres_request.serialize())
        more_magic_rr = async_mock.MagicMock(
            get_or_fetch_local_tails_path=async_mock.CoroutineMock(
                return_value="/tmp/sample/tails/path"
            )
        )
        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            test_module, "AttachDecorator", autospec=True
        ) as mock_attach_decorator, async_mock.patch.object(
            test_module, "RevocationRegistry", autospec=True
        ) as mock_rr:
            mock_rr.from_definition = async_mock.MagicMock(return_value=more_magic_rr)

            mock_attach_decorator.data_base64 = async_mock.MagicMock(
                return_value=mock_attach_decorator
            )

            req_creds = await indy_proof_req_preview2indy_requested_creds(
                indy_proof_req, holder=self.holder
            )
            assert not req_creds["self_attested_attributes"]
            assert len(req_creds["requested_attributes"]) == 2
            assert len(req_creds["requested_predicates"]) == 1

            (px_rec_out, pres_msg) = await self.manager.create_pres(
                px_rec_in, req_creds
            )
            save_ex.assert_called_once()
            assert px_rec_out.state == V20PresExRecord.STATE_PRESENTATION_SENT

    async def test_create_pres_proof_req_non_revoc_interval_none(self):
        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        indy_proof_req["non_revoked"] = None  # simulate interop with indy-vcx
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(pres_request=pres_request.serialize())

        more_magic_rr = async_mock.MagicMock(
            get_or_fetch_local_tails_path=async_mock.CoroutineMock(
                return_value="/tmp/sample/tails/path"
            )
        )
        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            test_module, "AttachDecorator", autospec=True
        ) as mock_attach_decorator, async_mock.patch.object(
            test_module, "RevocationRegistry", autospec=True
        ) as mock_rr:
            mock_rr.from_definition = async_mock.MagicMock(return_value=more_magic_rr)

            mock_attach_decorator.data_base64 = async_mock.MagicMock(
                return_value=mock_attach_decorator
            )

            req_creds = await indy_proof_req_preview2indy_requested_creds(
                indy_proof_req, holder=self.holder
            )
            assert not req_creds["self_attested_attributes"]
            assert len(req_creds["requested_attributes"]) == 2
            assert len(req_creds["requested_predicates"]) == 1

            (px_rec_out, pres_msg) = await self.manager.create_pres(
                px_rec_in, req_creds
            )
            save_ex.assert_called_once()
            assert px_rec_out.state == V20PresExRecord.STATE_PRESENTATION_SENT

    async def test_create_pres_self_asserted(self):
        PRES_PREVIEW_SELFIE = IndyPresPreview(
            attributes=[
                IndyPresAttrSpec(name="player", value="Richie Knucklez"),
                IndyPresAttrSpec(
                    name="screenCapture",
                    mime_type="image/png",
                    value="aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
                ),
            ],
            predicates=[
                IndyPresPredSpec(
                    name="highScore",
                    cred_def_id=None,
                    predicate=">=",
                    threshold=1000000,
                )
            ],
        )
        indy_proof_req = await PRES_PREVIEW_SELFIE.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(pres_request=pres_request.serialize())

        more_magic_rr = async_mock.MagicMock(
            get_or_fetch_local_tails_path=async_mock.CoroutineMock(
                return_value="/tmp/sample/tails/path"
            )
        )
        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            test_module, "AttachDecorator", autospec=True
        ) as mock_attach_decorator, async_mock.patch.object(
            test_module, "RevocationRegistry", autospec=True
        ) as mock_rr:
            mock_rr.from_definition = async_mock.MagicMock(return_value=more_magic_rr)

            mock_attach_decorator.data_base64 = async_mock.MagicMock(
                return_value=mock_attach_decorator
            )

            req_creds = await indy_proof_req_preview2indy_requested_creds(
                indy_proof_req, holder=self.holder
            )
            assert len(req_creds["self_attested_attributes"]) == 3
            assert not req_creds["requested_attributes"]
            assert not req_creds["requested_predicates"]

            (px_rec_out, pres_msg) = await self.manager.create_pres(
                px_rec_in, req_creds
            )
            save_ex.assert_called_once()
            assert px_rec_out.state == V20PresExRecord.STATE_PRESENTATION_SENT

    async def test_create_pres_no_revocation(self):
        Ledger = async_mock.MagicMock(BaseLedger, autospec=True)
        self.ledger = Ledger()
        self.ledger.get_schema = async_mock.CoroutineMock(
            return_value=async_mock.MagicMock()
        )
        self.ledger.get_credential_definition = async_mock.CoroutineMock(
            return_value={"value": {"revocation": None}}
        )
        self.profile.context.injector.bind_instance(BaseLedger, self.ledger)

        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(pres_request=pres_request.serialize())

        Holder = async_mock.MagicMock(IndyHolder, autospec=True)
        self.holder = Holder()
        get_creds = async_mock.CoroutineMock(
            return_value=(
                {
                    "cred_info": {"referent": "dummy_reft"},
                    "attrs": {
                        "player": "Richie Knucklez",
                        "screenCapture": "aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
                        "highScore": "1234560",
                    },
                },  # leave this comma: return a tuple
            )
        )
        self.holder.get_credentials_for_presentation_request_by_referent = get_creds
        self.holder.get_credential = async_mock.CoroutineMock(
            return_value=json.dumps(
                {
                    "schema_id": S_ID,
                    "cred_def_id": CD_ID,
                    "rev_reg_id": None,
                    "cred_rev_id": None,
                }
            )
        )
        self.holder.create_presentation = async_mock.CoroutineMock(return_value="{}")
        self.profile.context.injector.bind_instance(IndyHolder, self.holder)

        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            test_module, "AttachDecorator", autospec=True
        ) as mock_attach_decorator:

            mock_attach_decorator.data_base64 = async_mock.MagicMock(
                return_value=mock_attach_decorator
            )

            req_creds = await indy_proof_req_preview2indy_requested_creds(
                indy_proof_req, holder=self.holder
            )

            (px_rec_out, pres_msg) = await self.manager.create_pres(
                px_rec_in, req_creds
            )
            save_ex.assert_called_once()
            assert px_rec_out.state == V20PresExRecord.STATE_PRESENTATION_SENT

    async def test_create_pres_bad_revoc_state(self):
        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(pres_request=pres_request.serialize())

        Holder = async_mock.MagicMock(IndyHolder, autospec=True)
        self.holder = Holder()
        get_creds = async_mock.CoroutineMock(
            return_value=(
                {
                    "cred_info": {"referent": "dummy_reft"},
                    "attrs": {
                        "player": "Richie Knucklez",
                        "screenCapture": "aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
                        "highScore": "1234560",
                    },
                },  # leave this comma: return a tuple
            )
        )
        self.holder.get_credentials_for_presentation_request_by_referent = get_creds

        self.holder.get_credential = async_mock.CoroutineMock(
            return_value=json.dumps(
                {
                    "schema_id": S_ID,
                    "cred_def_id": CD_ID,
                    "rev_reg_id": RR_ID,
                    "cred_rev_id": 1,
                }
            )
        )
        self.holder.create_presentation = async_mock.CoroutineMock(return_value="{}")
        self.holder.create_revocation_state = async_mock.CoroutineMock(
            side_effect=test_module.IndyHolderError("Problem", {"message": "Nope"})
        )
        self.profile.context.injector.bind_instance(IndyHolder, self.holder)

        more_magic_rr = async_mock.MagicMock(
            get_or_fetch_local_tails_path=async_mock.CoroutineMock(
                return_value="/tmp/sample/tails/path"
            )
        )
        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            test_module, "AttachDecorator", autospec=True
        ) as mock_attach_decorator, async_mock.patch.object(
            test_module, "RevocationRegistry", autospec=True
        ) as mock_rr:
            mock_rr.from_definition = async_mock.MagicMock(return_value=more_magic_rr)

            mock_attach_decorator.data_base64 = async_mock.MagicMock(
                return_value=mock_attach_decorator
            )

            req_creds = await indy_proof_req_preview2indy_requested_creds(
                indy_proof_req, holder=self.holder
            )

            with self.assertRaises(test_module.IndyHolderError):
                await self.manager.create_pres(px_rec_in, req_creds)

    async def test_create_pres_multi_matching_proposal_creds_names(self):
        indy_proof_req = await PRES_PREVIEW_NAMES.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(pres_request=pres_request.serialize())

        Holder = async_mock.MagicMock(IndyHolder, autospec=True)
        self.holder = Holder()
        get_creds = async_mock.CoroutineMock(
            return_value=(
                {
                    "cred_info": {
                        "referent": "dummy_reft_0",
                        "cred_def_id": CD_ID,
                        "attrs": {
                            "player": "Richie Knucklez",
                            "screenCapture": "aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
                            "highScore": "1234560",
                        },
                    }
                },
                {
                    "cred_info": {
                        "referent": "dummy_reft_1",
                        "cred_def_id": CD_ID,
                        "attrs": {
                            "player": "Richie Knucklez",
                            "screenCapture": "aW1hZ2luZSBhbm90aGVyIHNjcmVlbiBjYXB0dXJl",
                            "highScore": "1515880",
                        },
                    }
                },
            )
        )
        self.holder.get_credentials_for_presentation_request_by_referent = get_creds
        self.holder.get_credential = async_mock.CoroutineMock(
            return_value=json.dumps(
                {
                    "schema_id": S_ID,
                    "cred_def_id": CD_ID,
                    "rev_reg_id": RR_ID,
                    "cred_rev_id": 1,
                }
            )
        )
        self.holder.create_presentation = async_mock.CoroutineMock(return_value="{}")
        self.holder.create_revocation_state = async_mock.CoroutineMock(
            return_value=json.dumps(
                {
                    "witness": {"omega": "1 ..."},
                    "rev_reg": {"accum": "21 ..."},
                    "timestamp": NOW,
                }
            )
        )
        self.profile.context.injector.bind_instance(IndyHolder, self.holder)

        more_magic_rr = async_mock.MagicMock(
            get_or_fetch_local_tails_path=async_mock.CoroutineMock(
                return_value="/tmp/sample/tails/path"
            )
        )
        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            test_module, "AttachDecorator", autospec=True
        ) as mock_attach_decorator, async_mock.patch.object(
            test_module, "RevocationRegistry", autospec=True
        ) as mock_rr:
            mock_rr.from_definition = async_mock.MagicMock(return_value=more_magic_rr)

            mock_attach_decorator.data_base64 = async_mock.MagicMock(
                return_value=mock_attach_decorator
            )

            req_creds = await indy_proof_req_preview2indy_requested_creds(
                indy_proof_req, preview=PRES_PREVIEW_NAMES, holder=self.holder
            )
            assert not req_creds["self_attested_attributes"]
            assert len(req_creds["requested_attributes"]) == 1
            assert len(req_creds["requested_predicates"]) == 1

            (px_rec_out, pres_msg) = await self.manager.create_pres(
                px_rec_in, req_creds
            )
            save_ex.assert_called_once()
            assert px_rec_out.state == V20PresExRecord.STATE_PRESENTATION_SENT

    async def test_no_matching_creds_for_proof_req(self):
        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(pres_request=pres_request.serialize())
        get_creds = async_mock.CoroutineMock(return_value=())
        self.holder.get_credentials_for_presentation_request_by_referent = get_creds

        with self.assertRaises(ValueError):
            await indy_proof_req_preview2indy_requested_creds(
                indy_proof_req, holder=self.holder
            )

        get_creds = async_mock.CoroutineMock(
            return_value=(
                {
                    "cred_info": {"referent": "dummy_reft"},
                    "attrs": {
                        "player": "Richie Knucklez",
                        "screenCapture": "aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
                        "highScore": "1234560",
                    },
                },  # leave this comma: return a tuple
            )
        )
        self.holder.get_credentials_for_presentation_request_by_referent = get_creds

    async def test_receive_pres(self):
        connection_record = async_mock.MagicMock(connection_id=CONN_ID)
        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        indy_proof = {
            "proof": {"proofs": []},
            "requested_proof": {
                "revealed_attrs": {
                    "0_player_uuid": {
                        "sub_proof_index": 0,
                        "raw": "Richie Knucklez",
                        "encoded": "12345678901234567890",
                    },
                    "1_screencapture_uuid": {
                        "sub_proof_index": 0,
                        "raw": "aW1hZ2luZSBhIHNjcmVlbiBjYXB0dXJl",
                        "encoded": "98765432109876543210",
                    },
                },
                "self_attested_attrs": {},
                "unrevealed_attrs": {},
                "predicates": {"0_highscore_GE_uuid": {"sub_proof_index": 0}},
            },
            "identifiers": [
                {
                    "schema_id": S_ID,
                    "cred_def_id": CD_ID,
                    "rev_reg_id": None,
                    "timestamp": None,
                }
            ],
        }
        pres_proposal = V20PresProposal(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            proposal_attach=[
                AttachDecorator.data_base64(PRES_PREVIEW.serialize(), ident="indy")
            ],
        )
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        pres = V20Pres(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            presentations_attach=[
                AttachDecorator.data_base64(indy_proof, ident="indy")
            ],
        )

        px_rec_dummy = V20PresExRecord(
            pres_proposal=pres_proposal.serialize(),
            pres_request=pres_request.serialize(),
        )

        # cover by_format property
        by_format = px_rec_dummy.by_format
        assert by_format.get("pres_proposal").get("indy") == PRES_PREVIEW.serialize()
        assert by_format.get("pres_request").get("indy") == indy_proof_req

        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            V20PresExRecord, "retrieve_by_tag_filter", autospec=True
        ) as retrieve_ex, async_mock.patch.object(
            self.profile,
            "session",
            async_mock.MagicMock(return_value=self.profile.session()),
        ) as session:
            retrieve_ex.side_effect = [
                StorageNotFoundError("no such record"),  # cover out-of-band
                px_rec_dummy,
            ]
            px_rec_out = await self.manager.receive_pres(pres, connection_record)
            assert retrieve_ex.call_count == 2
            save_ex.assert_called_once()
            assert px_rec_out.state == (V20PresExRecord.STATE_PRESENTATION_RECEIVED)

    async def test_receive_pres_bait_and_switch(self):
        connection_record = async_mock.MagicMock(connection_id=CONN_ID)
        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        indy_proof_x = {
            "proof": {"proofs": []},
            "requested_proof": {
                "revealed_attrs": {
                    "0_player_uuid": {
                        "sub_proof_index": 0,
                        "raw": "Richie Knucklez",
                        "encoded": "12345678901234567890",
                    },
                    "1_screencapture_uuid": {  # mismatch vs PRES_PREVIEW
                        "sub_proof_index": 0,
                        "raw": "bm90IHRoZSBzYW1lIHNjcmVlbiBjYXB0dXJl",
                        "encoded": "98765432109876543210",
                    },
                },
                "self_attested_attrs": {},
                "unrevealed_attrs": {},
                "predicates": {"0_highscore_GE_uuid": {"sub_proof_index": 0}},
            },
            "identifiers": [
                {
                    "schema_id": S_ID,
                    "cred_def_id": CD_ID,
                    "rev_reg_id": None,
                    "timestamp": None,
                }
            ],
        }
        pres_proposal = V20PresProposal(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            proposal_attach=[
                AttachDecorator.data_base64(PRES_PREVIEW.serialize(), ident="indy")
            ],
        )
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        pres_x = V20Pres(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            presentations_attach=[
                AttachDecorator.data_base64(indy_proof_x, ident="indy")
            ],
        )

        px_rec_dummy = V20PresExRecord(
            pres_proposal=pres_proposal.serialize(),
            pres_request=pres_request.serialize(),
            pres=pres_x.serialize(),
        )
        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            V20PresExRecord, "retrieve_by_tag_filter", autospec=True
        ) as retrieve_ex:
            retrieve_ex.return_value = px_rec_dummy
            with self.assertRaises(V20PresManagerError) as context:
                await self.manager.receive_pres(pres_x, connection_record)
            assert "mismatches" in str(context.exception)

    async def test_receive_pres_connection_less(self):
        px_rec_dummy = V20PresExRecord()
        message = async_mock.MagicMock()

        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            V20PresExRecord, "retrieve_by_tag_filter", autospec=True
        ) as retrieve_ex, async_mock.patch.object(
            self.profile,
            "session",
            async_mock.MagicMock(return_value=self.profile.session()),
        ) as session:
            retrieve_ex.return_value = px_rec_dummy
            px_rec_out = await self.manager.receive_pres(message, None)
            retrieve_ex.assert_called_once_with(
                session.return_value, {"thread_id": message._thread_id}, None
            )
            save_ex.assert_called_once()

            assert px_rec_out.state == (V20PresExRecord.STATE_PRESENTATION_RECEIVED)

    async def test_verify_pres(self):
        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        indy_proof = {
            "proof": {"proofs": []},
            "requested_proof": {
                "revealed_attrs": {
                    "0_player_uuid": {
                        "sub_proof_index": 0,
                        "raw": "Richie Knucklez",
                        "encoded": "12345678901234567890",
                    },
                    "1_screencapture_uuid": {
                        "sub_proof_index": 0,
                        "raw": "cG90YXRv",
                        "encoded": "98765432109876543210",
                    },
                },
                "self_attested_attrs": {},
                "unrevealed_attrs": {},
                "predicates": {"0_highscore_GE_uuid": {"sub_proof_index": 0}},
            },
            "identifiers": [
                {
                    "schema_id": S_ID,
                    "cred_def_id": CD_ID,
                    "rev_reg_id": None,
                    "timestamp": None,
                }
            ],
        }
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            will_confirm=True,
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        pres = V20Pres(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            presentations_attach=[
                AttachDecorator.data_base64(indy_proof, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(
            pres_request=pres_request.serialize(),
            pres=pres.serialize(),
        )

        with async_mock.patch.object(V20PresExRecord, "save", autospec=True) as save_ex:
            px_rec_out = await self.manager.verify_pres(px_rec_in)
            save_ex.assert_called_once()

            assert px_rec_out.state == (V20PresExRecord.STATE_DONE)

    async def test_verify_pres_with_revocation(self):
        indy_proof_req = await PRES_PREVIEW.indy_proof_request(
            name=PROOF_REQ_NAME,
            version=PROOF_REQ_VERSION,
            nonce=PROOF_REQ_NONCE,
            ledger=self.ledger,
        )
        indy_proof = {
            "proof": {"proofs": []},
            "requested_proof": {
                "revealed_attrs": {
                    "0_player_uuid": {
                        "sub_proof_index": 0,
                        "raw": "Richie Knucklez",
                        "encoded": "12345678901234567890",
                    },
                    "1_screencapture_uuid": {
                        "sub_proof_index": 0,
                        "raw": "cG90YXRv",
                        "encoded": "98765432109876543210",
                    },
                },
                "self_attested_attrs": {},
                "unrevealed_attrs": {},
                "predicates": {"0_highscore_GE_uuid": {"sub_proof_index": 0}},
            },
            "identifiers": [
                {
                    "schema_id": S_ID,
                    "cred_def_id": CD_ID,
                    "rev_reg_id": RR_ID,
                    "timestamp": NOW,
                }
            ],
        }
        pres_request = V20PresRequest(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            request_presentations_attach=[
                AttachDecorator.data_base64(indy_proof_req, ident="indy")
            ],
        )
        pres = V20Pres(
            formats=[
                V20PresFormat(
                    attach_id="indy",
                    format_=V20PresFormat.Format.INDY.aries,
                )
            ],
            presentations_attach=[
                AttachDecorator.data_base64(indy_proof, ident="indy")
            ],
        )
        px_rec_in = V20PresExRecord(
            pres_request=pres_request.serialize(),
            pres=pres.serialize(),
        )

        with async_mock.patch.object(V20PresExRecord, "save", autospec=True) as save_ex:
            px_rec_out = await self.manager.verify_pres(px_rec_in)
            save_ex.assert_called_once()

            assert px_rec_out.state == (V20PresExRecord.STATE_DONE)

    async def test_send_pres_ack(self):
        px_rec = V20PresExRecord()

        responder = MockResponder()
        self.profile.context.injector.bind_instance(BaseResponder, responder)

        await self.manager.send_pres_ack(px_rec)
        messages = responder.messages
        assert len(messages) == 1

    async def test_send_pres_ack_no_responder(self):
        px_rec = V20PresExRecord()

        self.profile.context.injector.clear_binding(BaseResponder)
        await self.manager.send_pres_ack(px_rec)

    async def test_receive_pres_ack(self):
        conn_record = async_mock.MagicMock(connection_id=CONN_ID)

        px_rec_dummy = V20PresExRecord()
        message = async_mock.MagicMock()

        with async_mock.patch.object(
            V20PresExRecord, "save", autospec=True
        ) as save_ex, async_mock.patch.object(
            V20PresExRecord, "retrieve_by_tag_filter", autospec=True
        ) as retrieve_ex:
            retrieve_ex.return_value = px_rec_dummy
            px_rec_out = await self.manager.receive_pres_ack(message, conn_record)
            save_ex.assert_called_once()

            assert px_rec_out.state == V20PresExRecord.STATE_DONE
