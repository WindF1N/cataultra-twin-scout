from __future__ import annotations


TURBO_TOKEN_LIST = """
query TurboTokenList($pagination: CursorPaginationInput!, $sort: TurboTokenListSortInput, $filter: TurboTokenListFilterInput) {
  turboTokenList(pagination: $pagination, sort: $sort, filter: $filter) {
    items {
      avatarUrl
      buysCount
      creator { id avatarToken profileName __typename }
      description
      endDate
      id
      initialPrice
      name
      price
      rank
      sellsCount
      speedMode
      startDate
      symbol
      uniqueTradersCount
      volumeUsdtDrops
      __typename
    }
    meta { firstCursor hasNextItems hasPreviousItems lastCursor __typename }
    __typename
  }
}
"""


TURBO_TOKEN_FAIR_DATA = """
query TurboTokenFairData($tokenId: String!) {
  turboTokenFairData(tokenId: $tokenId) {
    fairHash
    fairSalt
    speedTicksInSecond
    ticksArray
    __typename
  }
}
"""

