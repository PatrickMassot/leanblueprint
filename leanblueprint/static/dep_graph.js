var simulation = d3.forceSimulation()
    .force("link", d3.forceLink().id(function(d) { return d.id; }))
    .force("charge", d3.forceManyBody().strength(-50))
    .force("x", d3.forceX())
    .force("y", d3.forceY());


simulation
    .nodes(graph.nodes)
    .on("tick", ticked);

simulation.force("link")
    .links(graph.links);


function ticked() {
    link
        .attr("x1", function(d) { return d.source.x; })
        .attr("y1", function(d) { return d.source.y; })
        .attr("x2", function(d) { return d.target.x; })
        .attr("y2", function(d) { return d.target.y; });

    node
        .attr("cx", function(d) { return d.x; })
        .attr("cy", function(d) { return d.y; });
  }

function dragstarted(d) {
  if (!d3.event.active) simulation.alphaTarget(0.3).restart();
  d.fx = d.x;
  d.fy = d.y;
}

function dragged(d) {
  d.fx = d3.event.x;
  d.fy = d3.event.y;
}

function dragended(d) {
  if (!d3.event.active) simulation.alphaTarget(0);
  d.fx = null;
  d.fy = null;
}

const zoom = d3.zoom()
      .scaleExtent([1, 8])
      .on("zoom", zoomed);

var svg = d3.select("svg")

marker = svg.append("svg:defs").append("svg:marker")
    .attr("id", "arrow")
    .attr("refX", 6)
    .attr("refY", 3)
    .attr("markerWidth", 6)
    .attr("markerHeight", 6)
    .attr("orient", "auto")
    .append("path")
    .attr("d", "M 0 0 6 3 0 6 1.5 3")
    .style("fill", "black");

function zoomed() {
	  const {transform} = d3.event;
	  content.attr("transform", transform);
	  content.attr("stroke-width", 1 / transform.k);
}



var content = svg.append("g")
var link = content.append("g")
    .attr("class", "links")
    .selectAll("line")
    .data(graph.links)
    .enter().append("line")
		.attr("marker-end", "url(#arrow)");


var node = content.append("g")
      .attr("class", "nodes")
    .selectAll("circle")
    .data(graph.nodes)
    .enter().append("circle")
    .attr("r", 1.5)
    .on("mouseover", function(){
			var obj = d3.select(this);
			if (obj.classed("active")) {
  			obj.classed("activehighlight", true);
			} else {
  			obj.classed("highlight", true);
			}
		})
		.on("mouseout", function(d) {
			    d3.select(this).classed("highlight", false);
			    d3.select(this).classed("activehighlight", false);
          } )
    .on('click', function(d,i) {
            // d - datum
            // i - identifier or index
            // this - the `<circle>` that was clicked
           d3.selectAll("circle").classed("active highlight", false); 
           d3.select(this).classed("active activehighlight", true); 
					 $('.thm').hide();
					 $('#' + CSS.escape(d.id)).show();
        })
    .call(d3.drag()
          .on("start", dragstarted)
          .on("drag", dragged)
          .on("end", dragended));

  node.append("title")
      .text(function(d) { return d.id; });


function fitZoom() {
	console.log('Fitting');
  const width = 100;
  const height = 100;
  const box = content.node().getBBox();
  const center_x = (box.x + box.width)/2
  const center_y = (box.y + box.height)/2
  console.log('width', width);
  console.log('height', height);
  console.log('box', box);
  svg.transition().duration(750).call(
		zoom.transform,
		d3.zoomIdentity
		  .translate(width / 2, height / 2)
		  .scale(0.9/ Math.max(box.width / width, box.height / height)),
//		d3.mouse(svg.node())
	  );
}

content.call(zoom);

/*
var i = 0;
while(simulation.alpha() > 1e-12 && i++ < 5000) simulation.tick();
console.log('I', i, 'alpha', simulation.alpha())
*/

// This is a horrible hack but nothing else works
setTimeout(fitZoom, 1000)

