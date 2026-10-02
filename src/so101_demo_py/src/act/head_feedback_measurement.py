"""Evaluate a complete stopped workload window without granting motion.

The caller retains and seals the original window and its workload identities.
These computations do not prove CUDA execution, payload validity or approval.
"""

import math

from .head_feedback import FeedbackPolicy, nanoseconds
from .head_search_timing_params import nearest_rank_percentile


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('HEAD_WINDOW_NUMBER_INVALID')
    return float(value)


def _stamp(value):
    if type(value) is not int or value <= 0:
        raise ValueError('HEAD_WINDOW_SOURCE_INVALID')
    return value


def _series(values):
    if type(values) is not list or not values:
        raise ValueError('HEAD_WINDOW_SERIES_MISSING')
    return values


def _quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered)-1)*probability
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] + (ordered[high]-ordered[low])*(position-low)


def _distribution(values):
    checked = [_number(value) for value in _series(values)]
    return dict(count=len(checked), p50=_quantile(checked, .5),
                p95=_quantile(checked, .95), p99=_quantile(checked, .99),
                max=max(checked), negative_count=0)


def _messages(values, *, start, end, minimum, source_period=None):
    records = _series(values)
    if len(records) < minimum:
        raise ValueError('HEAD_WINDOW_MESSAGE_COUNT')
    identities, source_gaps, receipt_gaps = {}, [], []
    previous_source = previous_receipt = None
    for sample in records:
        if not isinstance(sample, dict) or sample.get('valid') is not True:
            raise ValueError('HEAD_WINDOW_ORIGINAL_INVALID')
        source = _stamp(sample['source_ns'])
        receipt = nanoseconds(_number(sample['wall_s']))
        if not start <= receipt <= end:
            raise ValueError('HEAD_WINDOW_RECEIPT_OUTSIDE_WINDOW')
        if previous_source is not None:
            source_gap = (source-previous_source)*1e-9
            receipt_gap = (receipt-previous_receipt)*1e-9
            if source_gap <= 0 or receipt_gap <= 0:
                raise ValueError('HEAD_WINDOW_MESSAGE_REGRESSION')
            if source_period is not None and abs(source_gap-source_period) > 1e-6:
                raise ValueError('HEAD_WINDOW_SOURCE_PERIOD')
            source_gaps.append(source_gap)
            receipt_gaps.append(receipt_gap)
        identities[source] = sample
        previous_source, previous_receipt = source, receipt
    if (records[-1]['source_ns']-records[0]['source_ns'])*1e-9 < 19.:
        raise ValueError('HEAD_WINDOW_SIMULATION_COVERAGE')
    return identities, source_gaps, receipt_gaps


def _original(copy, identities, wall_before):
    if not isinstance(copy, dict) or copy.get('valid') is not True:
        raise ValueError('HEAD_WINDOW_SNAPSHOT_INVALID')
    source = _stamp(copy['source_ns'])
    receipt = nanoseconds(_number(copy['wall_s']))
    original = identities.get(source)
    if original is None or copy != original or receipt > wall_before:
        raise ValueError('HEAD_WINDOW_SNAPSHOT_NOT_ORIGINAL')
    return source, receipt


def _within(values, bound):
    if any(value > bound for value in values):
        raise ValueError('HEAD_WINDOW_OBSERVATION_EXCEEDS_BOUND')


def evaluate_feedback_window(window, *, stop_latency_s):
    """Refuse the entire window on a bad observation; never filter or clamp.

    Message and decision lists stay in observed order. Linear quantiles apply
    only to the new feedback policy. The existing camera seed formulas retain
    their nearest-rank p99.9 and original 10 ms/clock-resolution margins.
    """
    try:
        return _evaluate(window, stop_latency_s)
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError('HEAD_WINDOW_FIELDS_INVALID') from error


def _evaluate(window, stop_latency_s):
    start = nanoseconds(_number(window['start_wall_s']))
    end = nanoseconds(_number(window['end_wall_s']))
    if end-start != 20_000_000_000:
        raise ValueError('HEAD_WINDOW_DURATION')
    stop_latency = _number(stop_latency_s)
    resolution = _number(window['clock_resolution_s'])
    if resolution <= 0:
        raise ValueError('HEAD_WINDOW_CLOCK_RESOLUTION')
    joints, joint_source, joint_wall = _messages(window['joint_messages'],
        start=start, end=end, minimum=1900, source_period=.01)
    cameras, camera_source, camera_wall = _messages(window['camera_messages'],
        start=start, end=end, minimum=190, source_period=.1)
    infos, _, _ = _messages(window['info_messages'],
        start=start, end=end, minimum=190, source_period=.1)
    _, clock_source, clock_wall = _messages(window['clock_messages'],
        start=start, end=end, minimum=2)
    decisions = _series(window['decisions'])
    if len(decisions) < 3900:
        raise ValueError('HEAD_WINDOW_DECISION_COUNT')
    joint_receipt_ages, joint_source_ages, camera_source_ages = [], [], []
    decision_gaps = []
    previous_wall = previous_sim = None
    for decision in decisions:
        clocks = decision['clocks']
        before = nanoseconds(_number(clocks['wall_before_s']))
        after = nanoseconds(_number(clocks['wall_after_s']))
        sim = _stamp(clocks['sim_ns'])
        if not start <= before <= after <= end:
            raise ValueError('HEAD_WINDOW_DECISION_CLOCK')
        if previous_wall is not None:
            if before <= previous_wall or sim <= previous_sim:
                raise ValueError('HEAD_WINDOW_DECISION_CLOCK_REGRESSION')
            decision_gaps.append((after-previous_wall)*1e-9)
        joint_stamp, joint_receipt = _original(decision['joint'], joints, before)
        camera_stamp, _ = _original(decision['camera'], cameras, before)
        joint_receipt_ages.append((after-joint_receipt)*1e-9)
        joint_source_ages.append((sim-joint_stamp)*1e-9)
        camera_source_ages.append((sim-camera_stamp)*1e-9)
        previous_wall, previous_sim = after, sim
    if (decisions[-1]['clocks']['sim_ns']-decisions[0]['clocks']['sim_ns'])*1e-9 < 19.:
        raise ValueError('HEAD_WINDOW_DECISION_COVERAGE')

    polls = [nanoseconds(_number(value)) for value in _series(window['watchdog_polls'])]
    if polls[0] < start or polls[-1] > end:
        raise ValueError('HEAD_WINDOW_WATCHDOG_OUTSIDE_WINDOW')
    poll_gaps = [(right-left)*1e-9 for left, right in zip(polls, polls[1:])]
    if any(gap <= 0 for gap in poll_gaps):
        raise ValueError('HEAD_WINDOW_WATCHDOG_REGRESSION')
    # Missing the beginning/end is also a missed poll.
    poll_gaps += [(polls[0]-start)*1e-9, (end-polls[-1])*1e-9]
    _within(poll_gaps, .010)

    frame_ages, skews, seen = [], [], set()
    previous_completion = start
    previous_image_source = 0
    for inference in _series(window['inferences']):
        source = _stamp(inference['source_ns'])
        frame = cameras.get(source)
        if frame is None or source in seen or source <= previous_image_source:
            raise ValueError('HEAD_WINDOW_INFERENCE_LINKAGE')
        seen.add(source)
        previous_image_source = source
        image = nanoseconds(_number(inference['image_received_wall_s']))
        info = nanoseconds(_number(inference['info_received_wall_s']))
        info_source = _stamp(inference['info_source_ns'])
        joint_source_stamp = _stamp(inference['joint_source_ns'])
        tf_source = _stamp(inference['tf_source_ns'])
        original_info = infos.get(info_source)
        causal_joint = joints.get(joint_source_stamp)
        if (info_source != source or original_info is None
                or info != nanoseconds(original_info['wall_s']) or causal_joint is None
                or joint_source_stamp > source or tf_source > source):
            raise ValueError('HEAD_WINDOW_INFERENCE_ORIGINALS')
        spread = (max(source, info_source, joint_source_stamp, tf_source)
                  - min(source, info_source, joint_source_stamp, tf_source))*1e-9
        if nanoseconds(_number(inference['source_skew_s'])) != nanoseconds(spread):
            raise ValueError('HEAD_WINDOW_SKEW_NOT_FROM_SOURCES')
        admission = nanoseconds(_number(inference['admission_wall_s']))
        completion = nanoseconds(_number(inference['completion_wall_s']))
        if (image != nanoseconds(frame['wall_s']) or not start <= info <= admission
                or not image <= admission <= completion <= end
                or admission < previous_completion
                or nanoseconds(causal_joint['wall_s']) > admission):
            raise ValueError('HEAD_WINDOW_INFERENCE_CLOCK')
        previous_completion = completion
        frame_ages.extend([(admission-image)*1e-9, (completion-image)*1e-9,
                           (admission-info)*1e-9, (completion-info)*1e-9])
        skews.append(spread)
    if seen != set(cameras) or seen != set(infos):
        raise ValueError('HEAD_WINDOW_INFERENCE_MISSING')

    raw_series = dict(joint_receipt_age_s=joint_receipt_ages,
        joint_source_age_s=joint_source_ages, camera_source_age_s=camera_source_ages,
        joint_source_period_s=joint_source, joint_receipt_period_s=joint_wall,
        camera_source_period_s=camera_source, camera_receipt_gap_s=camera_wall,
        clock_source_period_s=clock_source, clock_receipt_gap_s=clock_wall,
        decision_interval_s=decision_gaps, watchdog_interval_s=poll_gaps,
        camera_end_to_end_age_s=frame_ages, camera_source_skew_s=skews)
    distributions = {name: _distribution(values) for name, values in raw_series.items()}
    js = distributions['joint_source_period_s']['p50']
    jm = distributions['joint_receipt_period_s']['p50']
    cs = distributions['camera_source_period_s']['p50']
    cm = distributions['camera_receipt_gap_s']['p50']
    values = dict(
        joint_max_receipt_age_s=distributions['joint_receipt_age_s']['p99']+jm,
        joint_max_source_age_s=distributions['joint_source_age_s']['p99']+js,
        camera_interarrival_deadline_s=distributions['camera_receipt_gap_s']['p99']+jm,
        camera_max_source_age_s=distributions['camera_source_age_s']['p99']+cs,
        clock_interarrival_deadline_s=distributions['clock_receipt_gap_s']['p99']+jm,
        watchdog_period_s=.002, watchdog_reaction_limit_s=.010,
        revoker_connection_deadline_s=.002)
    FeedbackPolicy.parse(values)
    if (values['joint_max_source_age_s'] > 2*js
            or values['camera_max_source_age_s'] > 2*cs
            or values['camera_interarrival_deadline_s'] > 2*cm
            or values['joint_max_receipt_age_s'] >= stop_latency-.010
            or values['clock_interarrival_deadline_s'] >= stop_latency-.010):
        raise ValueError('HEAD_WINDOW_POLICY_CEILING')
    for population, field in (
            (joint_receipt_ages, 'joint_max_receipt_age_s'),
            (joint_source_ages, 'joint_max_source_age_s'),
            (camera_wall, 'camera_interarrival_deadline_s'),
            (camera_source_ages, 'camera_max_source_age_s'),
            (clock_wall, 'clock_interarrival_deadline_s')):
        _within(population, values[field])
    camera_values = dict(max_age_s=nearest_rank_percentile(frame_ages, .999)+.010,
                         max_skew_s=nearest_rank_percentile(skews, .999)+resolution)
    if camera_values['max_age_s'] > .15 or camera_values['max_skew_s'] > .05:
        raise ValueError('HEAD_WINDOW_CAMERA_CEILING')
    _within(frame_ages, camera_values['max_age_s'])
    _within(skews, camera_values['max_skew_s'])
    return dict(purpose='calibration', motion_authority=False,
        quantile='linear interpolation at (n-1)*p', values=values,
        camera_seed_values=camera_values, distributions=distributions,
        periods=dict(joint_source_p50_s=js, joint_receipt_p50_s=jm,
                     camera_source_p50_s=cs, camera_receipt_p50_s=cm),
        counts=dict(decisions=len(decisions), joint_messages=len(joints),
                    camera_messages=len(cameras), clock_messages=len(window['clock_messages']),
                    info_messages=len(infos),
                    inferences=len(seen), watchdog_polls=len(polls)),
        real_time_factor=(decisions[-1]['clocks']['sim_ns']-decisions[0]['clocks']['sim_ns'])/
            (nanoseconds(decisions[-1]['clocks']['wall_after_s'])-
             nanoseconds(decisions[0]['clocks']['wall_after_s'])),
        formulas=dict(joint_max_receipt_age_s='joint_receipt_age_s.p99 + joint_receipt_period_s.p50',
            joint_max_source_age_s='joint_source_age_s.p99 + joint_source_period_s.p50',
            camera_interarrival_deadline_s='camera_receipt_gap_s.p99 + joint_receipt_period_s.p50',
            camera_max_source_age_s='camera_source_age_s.p99 + camera_source_period_s.p50',
            clock_interarrival_deadline_s='clock_receipt_gap_s.p99 + joint_receipt_period_s.p50',
            max_age_s='nearest_rank_p99_9(camera_end_to_end_age_s) + .010 s',
            max_skew_s='nearest_rank_p99_9(camera_source_skew_s) + clock_resolution_s'))
