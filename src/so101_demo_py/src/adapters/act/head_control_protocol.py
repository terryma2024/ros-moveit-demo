"""Strict, bounded Head startup and incarnation-scoped close reply codecs."""
import struct

_PROOF = struct.Struct('>QBBBBHbbbBIHQQqqqqq')
_FIELDS = ('evaluation_id','wrapper_reason','witness_rejection','last_reset_reason','flags',
    'sample_count','failing_sample_index','failing_joint_index','last_reset_joint_index',
    '_reserved1','cumulative_observation_lock_losses','_reserved2','first_sequence','last_sequence',
    'first_sim_time_ns','last_sim_time_ns','first_received_ns','last_received_ns','evaluated_ns')


def _require(valid):
    if not valid:
        raise RuntimeError('HEAD_CONTROL_REPLY_INVALID')


def parse_proof_record(body):
    _require(type(body) is bytes and len(body)==80)
    p=dict(zip(_FIELDS,_PROOF.unpack(body)))
    _require(p.pop('_reserved1')==0 and p.pop('_reserved2')==0)
    wrapper=p['wrapper_reason'];flags=p['flags'];count=p['sample_count']
    _require(0<=wrapper<=8 and p['witness_rejection']<=7 and p['last_reset_reason']<=19
        and flags&~7==0 and count<=64)
    _require(-1<=p['failing_sample_index']<51 and -1<=p['failing_joint_index']<5
        and -1<=p['last_reset_joint_index']<5)
    samples=bool(flags&4);snapshot=bool(flags&1)
    sample_fields=('first_sequence','last_sequence','first_sim_time_ns','last_sim_time_ns',
                   'first_received_ns','last_received_ns')
    _require(samples==(count!=0))
    if not snapshot:
        _require(flags==0 and p['witness_rejection']==0 and p['last_reset_reason']==0
            and count==0 and all(p[k]==0 for k in (*sample_fields,'evaluated_ns'))
            and all(p[k]==-1 for k in ('failing_sample_index','failing_joint_index','last_reset_joint_index')))
    _require(all(p[k]>0 for k in sample_fields) if samples else all(p[k]==0 for k in sample_fields))
    if wrapper==7:
        _require(p['evaluation_id']==0 and not snapshot and p['cumulative_observation_lock_losses']==0)
    else:
        _require(p['evaluation_id']>0)
    if wrapper==8:_require(not snapshot and p['cumulative_observation_lock_losses']==0)
    if wrapper in (1,2,3):_require(not snapshot)
    if wrapper==6:_require(snapshot and p['witness_rejection']!=0)
    if wrapper==0:
        _require(flags==5 and p['witness_rejection']==0 and count>=51
            and p['failing_sample_index']==p['failing_joint_index']==-1
            and p['last_sequence']-p['first_sequence']==50
            and p['last_sim_time_ns']-p['first_sim_time_ns']==100_000_000
            and p['last_received_ns']>=p['first_received_ns']
            and p['evaluated_ns']>=p['last_received_ns']
            and p['evaluated_ns']-p['first_received_ns']<=200_000_000)
    return p


def _identity(body,offset):
    result={}
    for key in ('incarnation','boot'):
        _require(offset<len(body))
        length=body[offset];offset+=1
        _require(1<=length<=64 and offset+length<=len(body))
        value=body[offset:offset+length];offset+=length
        _require(all(32<=byte<=126 for byte in value))
        result[key]=value.decode('ascii')
    return result,offset


def identity_fields(identity,generation):
    _require(isinstance(identity,dict) and identity.get('role')==3
        and type(identity.get('role')) is int and identity.get('generation')==generation
        and type(identity.get('generation')) is int)
    for key in ('incarnation','boot'):
        _require(type(identity.get(key)) is str and 1<=len(identity[key])<=64
            and all(32<=ord(c)<=126 for c in identity[key]))
    return {key:identity[key] for key in ('role','generation','incarnation','boot')}


def parse_identity_scope(body,*,generation,close=False):
    _require(type(body) is bytes and 28<=len(body)<=154
        and body[:5]==(b'SOPD\x01' if close else b'SOPI\x01') and body[6:8]==b'\x03\x00'
        and body[5]<=(3 if close else 1) and int.from_bytes(body[8:16],'big')==generation)
    status=body[5];stored=int.from_bytes(body[16:24],'big')
    identity,offset=_identity(body,24);_require(offset==len(body))
    if close:
        if status==0:_require(stored==generation)
        if status==1:_require(stored==0)
        if status==2:_require(stored not in (0,generation))
    names=('ARMED_CLOSED','NOT_ARMED_CLOSED','REJECT_GENERATION','REJECT_IDENTITY') if close else ('AVAILABLE','REJECT_SCOPE')
    return dict(identity,role=3,generation=generation,stored_generation=stored,native_status=status,status=names[status])


def parse_prearm(body,*,generation):
    _require(type(body) is bytes and 110<=len(body)<=236 and body[:5]==b'SOPR\x01'
        and body[5]<=2 and body[6:8]==b'\x03\x00' and int.from_bytes(body[8:16],'big')==generation)
    status=body[5];stored=int.from_bytes(body[16:24],'big');reason=int.from_bytes(body[24:26],'big')
    _require(reason<=6)
    identity,offset=_identity(body,26);_require(offset+80==len(body))
    proof=parse_proof_record(body[offset:])
    if status<2:
        _require(reason==0 and generation>stored and proof['evaluation_id']>0
            and proof['wrapper_reason']!=7 and (status==0)==(proof['wrapper_reason']==0))
    else:
        _require(reason!=0 and proof['wrapper_reason']==7)
    return dict(identity,role=3,generation=generation,stored_generation=stored,
        native_status=status,status=('READY','NOT_READY','REJECT_SCOPE')[status],gate_reason=reason,proof=proof)


def parse_diagnostic_arm(body,*,generation):
    _require(type(body) is bytes and len(body)==104 and body[:5]==b'SOAR\x01'
        and body[5]<=1 and body[6]==3 and body[7]<=3
        and int.from_bytes(body[8:16],'big')==generation and body[18:24]==bytes(6))
    status=body[5];phase=body[7];reason=int.from_bytes(body[16:18],'big');_require(reason<=6)
    proof=parse_proof_record(body[24:]);_require(proof['evaluation_id']>0)
    if status==0:_require(phase==0 and reason==0 and proof['wrapper_reason']==0)
    elif phase==2:_require(reason!=0 and proof['wrapper_reason']==0)
    else:_require(phase in (1,3) and reason==0 and proof['wrapper_reason'] not in (0,7))
    return dict(role=3,generation=generation,status='ACK' if status==0 else 'REJECT',
        native_status=status,phase=('NONE','STOP_BEFORE','GATE_ARM','STOP_AFTER')[phase],gate_reason=reason,proof=proof)
