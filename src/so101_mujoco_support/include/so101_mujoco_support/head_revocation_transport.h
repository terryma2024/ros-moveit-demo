#ifndef SO101_MUJOCO_SUPPORT__HEAD_REVOCATION_TRANSPORT_H_
#define SO101_MUJOCO_SUPPORT__HEAD_REVOCATION_TRANSPORT_H_

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ABI 1: CLOCK_MONOTONIC originals, no capability or request bytes in evidence.
 * Phases: path, connect, request-peer, send, receive, reply-peer, deadline,
 * complete. Errors: config, path, peer, I/O, deadline, reply, rejection.
 */
typedef struct So101HeadRevocationResult
{
  uint32_t phase;
  uint32_t error_number;
  uint32_t reply_size;
  uint32_t phases_present;
  uint64_t entry_ns;
  uint64_t ack_ns;
  uint64_t ended_ns;
  uint64_t phases_ns[6];
  uint8_t reply[145];
} So101HeadRevocationResult;

uint32_t so101_head_revocation_abi(void);
uint32_t so101_head_revocation_result_size(void);
uint32_t so101_head_revocation_exchange(
  const char * path, const uint8_t * capability, uint64_t generation,
  uint32_t native_uid, int32_t native_pid, uint64_t native_start_ticks,
  uint64_t request_ns, uint64_t budget_ns, uint32_t operation,
  So101HeadRevocationResult * result);

#ifdef __cplusplus
}
#endif
#endif  /* SO101_MUJOCO_SUPPORT__HEAD_REVOCATION_TRANSPORT_H_ */
