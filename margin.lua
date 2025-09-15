-- margin.lua
function Image(img)
  img.attributes["class"] = (img.attributes["class"] or "") .. " column-margin"
  return img
end