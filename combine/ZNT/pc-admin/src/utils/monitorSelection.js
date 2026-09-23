/** Selected camera always occupies the first cell, including camera five in a four-cell grid. */
export function visibleCameras(cameras, selectedId, preferredIds, grid) {
  const count=[1,4,9,16].includes(grid)?grid:4
  const byId=new Map(cameras.map(c=>[c.id,c]))
  const ids=[...new Set([selectedId,...preferredIds,...byId.keys()])].filter(id=>byId.has(id)).slice(0,count)
  return [...ids.map(id=>byId.get(id)),...Array(count-ids.length).fill(null)]
}
