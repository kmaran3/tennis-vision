{{ config(materialized='view') }}
{% for tour in ['atp', 'wta'] %}
select *, '{{ tour|upper }}' as tour from {{ source('raw', tour ~ '_matches') }}
{% if not loop.last %} union all by name {% endif %}
{% endfor %}
