SELECT
  DATE(insert_timestamp) AS call_date,
  COUNT(DISTINCT internal_id) AS total_calls,
  COUNTIF(status = 'busy') AS busy_calls,
  COUNTIF(status = 'no-answer') AS no_answer_calls,
  COUNTIF(status = 'processed') AS successful_calls
FROM
  `docboard-561bf.docBoard.call_status_updates`
WHERE
  _PARTITIONTIME = TIMESTAMP("2025-06-01") -- Change "2025-06-01" to query a different month's partition
GROUP BY
  call_date
ORDER BY
  call_date ASC;



SELECT
  DATE(insert_timestamp) AS call_date,
  conversation_flag,
  COUNT(*) AS count_per_flag_per_day
FROM
  `docboard-561bf.docBoard.call_status_updates`
WHERE
  conversation_flag <> ''
  AND _PARTITIONTIME = TIMESTAMP("2025-06-01") -- Change "2025-06-01" to query a different month's partition
GROUP BY
  call_date,
  conversation_flag
ORDER BY
  call_date ASC,
  conversation_flag ASC;