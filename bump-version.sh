#!/bin/bash

RELEASE=$1
VERSION=${RELEASE/-*/}
CURRENT_RELEASE=$(git tag | sed -nr 's/^v([0-9].*)/\1/p' | sort -V | tail -1)
CURRENT_VERSION=${CURRENT_RELEASE/-*/}

if [[ -z "${VERSION}" ]]; then
    VERSION="${CURRENT_VERSION%.*}.$((${CURRENT_VERSION/*./} + 1))"
    RELEASE=${VERSION}
fi

TAG=v${RELEASE}

if [[ ! $RELEASE =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9]+)?$ ]]; then
    echo "VERSION must be a semantic version: MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-RELEASE"
    exit 1
fi

if [[ 'main' != "$(git branch --show-current)" ]]; then
    echo "Not on main git branch!"
    exit 1
fi

if [[ -n "$(git tag -l $TAG)" ]]; then
    echo "$RELEASE already exists"
    exit 1
fi

if [[ $RELEASE != "$(echo -e "${RELEASE}\n${CURRENT_RELEASE}" | sort -V | tail -1)" ]]; then
    echo "$RELEASE is not semantically newest"
    exit 1
fi

if [[ -n "$(git status --porcelain | grep -v '^?? ')" ]]; then
    echo "Cannot set version when working directory has differences"
fi

read -p "Make release ${RELEASE}? (Y/N) " CONTINUE
CONTINUE=$(echo "$CONTINUE" | tr '[:lower:]' '[:upper:]')

if [[ "$CONTINUE" != "Y" ]]; then
  echo "Invalid input. Please enter Y or y."
  exit 1
fi

# Set version and appVersion in helm chart
sed -i'' -e "s/^version: .*/version: ${RELEASE}/" helm/Chart.yaml
sed -i'' -e "s/^appVersion: .*/appVersion: ${RELEASE}/" helm/Chart.yaml

git add "${HELM_DIR}/Chart.yaml"
git commit -m "${TAG}"
git tag $TAG
git push origin main $TAG
