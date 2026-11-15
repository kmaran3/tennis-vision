select unnest(generate_series(date '1968-01-01', date '2030-12-31', interval 1 day))::date as date_day
