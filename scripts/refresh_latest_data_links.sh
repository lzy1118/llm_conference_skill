#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
latest_root="$repo_root/generated-data/最新数据"

mkdir -p "$latest_root/三大密码会" "$latest_root/四大安全会"

for conference in ASIACRYPT CRYPTO EUROCRYPT; do
  source_name=$(printf '%s' "$conference" | tr '[:upper:]' '[:lower:]')
  for year in 2020 2021 2022 2023 2024 2025; do
    target_dir="$latest_root/三大密码会/$conference/$year"
    mkdir -p "$target_dir"
    ln -sfn \
      "../../../../../outputs/crypto_2020_2025_author_affiliations/by_conference_year/${source_name}_${year}.csv" \
      "$target_dir/paper_metadata.csv"
  done
done

mkdir -p "$latest_root/三大密码会/全部年份"
ln -sfn \
  '../../../../outputs/crypto_2020_2025_author_affiliations/三大密码会_2020-2025_作者机构元数据.csv' \
  "$latest_root/三大密码会/全部年份/paper_metadata_2020-2025.csv"
ln -sfn \
  '../../../../outputs/crypto_2020_2025_author_affiliations/三大密码会_2020-2025_作者机构元数据.xlsx' \
  "$latest_root/三大密码会/全部年份/paper_metadata_2020-2025.xlsx"

for mapping in 'CCS:CCS' 'IEEE_S&P:ieee_s&p' 'NDSS:ndss' 'USENIX_SECURITY:usenix_security'; do
  display_name=${mapping%%:*}
  source_name=${mapping#*:}
  for year in 2020 2021 2022 2023 2024 2025; do
    target_dir="$latest_root/四大安全会/$display_name/$year"
    mkdir -p "$target_dir"
    ln -sfn \
      "../../../../full_output/${source_name}/${year}/author_metadata_dataset_${year}/paper_metadata.csv" \
      "$target_dir/paper_metadata.csv"
  done
done

ln -sfn '最新数据' "$repo_root/generated-data/latest"

find "$latest_root" -type l ! -exec test -e {} \; -print | while IFS= read -r broken_link; do
  printf 'Broken link: %s\n' "$broken_link" >&2
  exit 1
done

printf 'Latest verified data links refreshed: %s\n' "$latest_root"
