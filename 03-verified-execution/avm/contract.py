"""Compiled verification kernel for the paper, not a market settlement contract.

The immutable creation arguments stand in for an already registered proposal.
This deliberately narrow benchmark supports 1, 2, 4, 8, 16, 32, or 64 leaves;
the general off-chain protocol also supports padded non-power-of-two trees.
"""

from algopy import Bytes, Contract, Global, OnCompleteAction, Txn, UInt64, op, subroutine


class ExecutionVerifier(Contract):
    def approval_program(self) -> bool:
        assert Txn.on_completion == OnCompleteAction.NoOp
        assert Txn.rekey_to == Global.zero_address
        if Txn.application_id == 0:
            assert Txn.num_app_args == 6
            context = Txn.application_args(0)
            count_bytes = Txn.application_args(1)
            root = Txn.application_args(2)
            result = Txn.application_args(3)
            key = Txn.application_args(4)
            whole = Txn.application_args(5)
            assert context.length == 32
            assert count_bytes.length == 8
            count = op.btoi(count_bytes)
            assert count > 0 and count <= 64
            assert count & (count - 1) == 0
            assert root.length == 32 and result.length == 32
            assert key.length == 32 and whole.length == 32
            op.AppGlobal.put(b"ctx", context)
            op.AppGlobal.put(b"cnt", count)
            op.AppGlobal.put(b"root", root)
            op.AppGlobal.put(b"result", result)
            op.AppGlobal.put(b"key", key)
            op.AppGlobal.put(b"whole", whole)
            return True
        assert Txn.num_app_args > 0
        method = Txn.application_args(0)
        if method == b"budget":
            assert Txn.num_app_args == 1
            return True
        if method == b"whole":
            assert Txn.num_app_args == 2
            return op.sha256(Txn.application_args(1)) == op.AppGlobal.get_bytes(b"whole")
        assert method == b"member" or method == b"signed"
        if method == b"member":
            assert Txn.num_app_args == 6
        else:
            assert Txn.num_app_args == 7
        assert Txn.application_args(1) == op.AppGlobal.get_bytes(b"ctx")
        assert Txn.application_args(2).length == 8
        count = op.btoi(Txn.application_args(2))
        assert count == op.AppGlobal.get_uint64(b"cnt")
        assert Txn.application_args(3).length == 8
        index = op.btoi(Txn.application_args(3))
        assert index < count
        payload = Txn.application_args(4)
        proof = Txn.application_args(5)
        depth = UInt64(0)
        width = count
        while width > 1:
            width >>= 1
            depth += 1
        assert proof.length == depth * 32
        hashed = op.sha256(
            b"QM_EXEC_LEAF_V1\x00" + Txn.application_args(1)
            + Txn.application_args(2) + Txn.application_args(3) + op.sha256(payload)
        )
        pos = UInt64(0)
        while pos < depth:
            sibling = op.extract(proof, pos * 32, 32)
            if index & 1:
                hashed = op.sha256(b"QM_EXEC_NODE_V1\x00" + sibling + hashed)
            else:
                hashed = op.sha256(b"QM_EXEC_NODE_V1\x00" + hashed + sibling)
            index >>= 1
            pos += 1
        root = op.sha256(
            b"QM_EXEC_ROOT_V1\x00" + Txn.application_args(1)
            + Txn.application_args(2) + hashed
        )
        assert root == op.AppGlobal.get_bytes(b"root")
        if method == b"signed":
            signature = Txn.application_args(6)
            assert signature.length == 64
            message = op.sha256(
                b"QM_EXEC_AVM_RECEIPT_V1\x00" + Txn.application_args(1)
                + Txn.application_args(2) + root + op.AppGlobal.get_bytes(b"result")
            )
            assert op.ed25519verify_bare(message, signature, op.AppGlobal.get_bytes(b"key"))
        return True

    def clear_state_program(self) -> bool:
        return False
