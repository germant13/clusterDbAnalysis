#!/usr/bin/env python

'''
This library file contains functions for generating and manipulating Biopython
graphics objects.
'''

import colorsys
import itertools
import math
import numpy

from Bio.Graphics import GenomeDiagram
from Bio.SeqFeature import SeqFeature, FeatureLocation
from reportlab.lib import colors as rcolors

from sanitizeString import *
from ClusterFuncs import *
from TreeFuncs import splitTblastn

###########################################
# Functions for making SeqFeature objects #
###########################################

def makeSeqFeature(geneid, cur):
    '''
    Make a BioPython SeqFeature object for a gene with ITEP ID geneid
    '''

    geneinfo = getGeneInfo( [ geneid ], cur )
    geneinfo = geneinfo[0]
    start = int(geneinfo[5])
    stop = int(geneinfo[6])
    strand = int(geneinfo[8])
    feature = SeqFeature(FeatureLocation(start, stop), strand=strand, id=geneid)
    # This can be overwritten by other functions but we need a placeholder.
    feature.qualifiers["cluster_id"] = -1
    return feature

def makeSeqFeaturesForGeneNeighbors(genename, clusterrunid, cur):
    '''                                                                                                                                                                                                       
    Create seqFeature objects for a gene and its neighbors.

    genename is the ITEP ID for a gene.
    clusterrunid is a tuple (clusterid, runid) 

    The function returns a list of BioPython SeqFeature objects for the specified gene 
    and its neighbors.
    
    If the gene is not found it returns an empty list.
    '''
    outdata = getGeneNeighborhoods(genename, clusterrunid, cur)
    seqfeatures = []
    for neargene in outdata:
        feature = makeSeqFeature(neargene[1], cur)
        feature.qualifiers["cluster_id"] = int(neargene[8])
        seqfeatures.append(feature)
    return seqfeatures

def makeSeqObjectsForTblastnNeighbors(tblastn_id, clusterrunid, cur, N=200000):
    '''
    Given a tBLASTn ID and a dictionary from sanitized contig IDs (which is what will be 
    present in the TBLASTN id) to non-sanitized IDs (which are what is in the database),
    returns a list of seq objects INCLUDING the TBLASTN hit itself so that we can show that
    on the region drawing.

    We pick an N large enough to get at least one gene and then pick the closest one and get
    all of its neighbors with a call to makeSeqFeaturesForGeneNeighbors() and just tack the TBLASTN
    onto it. 
    '''
    # Lets first get the contig and start/stop locations (which tell us teh strand) out of    
    # the TBLASTN id. This returns a ValueError if it fails which the calling function can catch if needed. 
    sanitizedToNot = getSanitizedContigList(cur)

    # The tBLASTn ID holds information on where the hit was located.
    contig,start,stop = splitTblastn(tblastn_id)
    if contig in sanitizedToNot:
        contig = sanitizedToNot[contig]

    # Create a seq object for the TBLASTN hit itself
    start = int(start)
    stop = int(stop)
    if start < stop:
        strand = +1
    else:
        strand = -1
    tblastn_feature = SeqFeature(FeatureLocation(start, stop), strand=strand, id=tblastn_id)
    tblastn_feature.qualifiers["cluster_id"] = -1

    # Find the neighboring genes.
    neighboring_genes = getGenesInRegion(contig, start-N, stop+N, cur)
    if len(neighboring_genes) == 0:
        sys.stderr.write("WARNING: No neighboring genes found for TBLASTN hit %s within %d nucleotides in contig %s\n" %(tblastn_id, N, contig))
        return [ tblastn_feature ]
    else:
        neighboring_geneinfo = getGeneInfo(neighboring_genes, cur)

    # Find the closest gene to ours and get the clusters for those neighbors based on the specific clusterrunid                                                                                               
    minlen = N
    mingene = None
    minstrand = None
    for geneinfo in neighboring_geneinfo:
        genestart = int(geneinfo[5])
        geneend = int(geneinfo[6])
        distance = min( abs(genestart - start), abs(geneend - start), abs(genestart - stop), abs(geneend - stop))
        if distance < minlen:
            mingene = geneinfo[0]
            minlen = distance

    neighboring_features = makeSeqFeaturesForGeneNeighbors(mingene, clusterrunid, cur)

    # Add the TBLASTN itself and return it.
    neighboring_features.append(tblastn_feature)
    return neighboring_features

###############################
# Drawing functions           #
###############################

def regionlength(seqfeatures):
    ''' Find the beginning and end of nucleotides spanning a set of gene locations '''
    location = [(int(loc.location.start), int(loc.location.end)) for loc in seqfeatures]
    starts, ends = zip(*location)
    #have to compare both, as some are reversed
    start = max(max(starts),max(ends))
    end = min(min(starts),min(ends))
    return start, end

def make_region_drawing(seqfeatures, getcolor, centergenename, maxwidth, label=False):
    '''
    Makes a PNG figure for regions with a given color mapping, set of gene locations... 

    seqfeatures is a list of SeqFeature objects (with the cluster_id qualifier)
    getcolor is a map from cluster ID to the desired color
    centergenename is the ID (as in the seqFeature) for the gene you wish to have in the middle.
    maxwidth is the maximum width of the image (in pixels)

    if label is TRUE we add the cluster ID as a label to each of the arrows.

    TODO make auto-del tempfiles, or pass svg as string
    '''

    imgfileloc = "/tmp/%s.png" %(sanitizeString(centergenename, False))

    # Set up an entry genome diagram object                                                                                                                                                                   
    gd_diagram = GenomeDiagram.Diagram("Genome Region")
    gd_track_for_features = gd_diagram.new_track(1, name="Annotated Features")
    gd_feature_set = gd_track_for_features.new_set()

    # Some basic properties of the figure itself
    arrowshaft_height = 0.3
    arrowhead_length = 0.3
    default_fontsize = 30 # Font size for genome diagram labels
    scale = 20     #AA per px for the diagram

    # Build arrow objects for all of our features.
    for feature in seqfeatures:
        bordercol=rcolors.white

        if feature.id == centergenename:
            bordercol=rcolors.red
            centerdstart, centerend = int(feature.location.start), int(feature.location.end)
            centerdstrand = feature.strand
        color = getcolor[feature.qualifiers["cluster_id"]]

        gd_feature_set.add_feature(feature, name = str(feature.qualifiers["cluster_id"]),
                                   color=color, border = bordercol,
                                   sigil="ARROW", arrowshaft_height=arrowshaft_height, arrowhead_length = arrowhead_length,
                                   label=label,  label_angle=20, label_size = default_fontsize
                                   )

    start, end = regionlength(seqfeatures)
    pagew_px = maxwidth / scale
    #offset so start of gene of interest lines up in all the figures
    midcentergene = abs(centerend - centerdstart)/2 + min(centerdstart, centerend)
    l2mid = abs(midcentergene - start)
    r2mid = abs(midcentergene - end)
    roffset = float((pagew_px/2) - (l2mid/scale))
    loffset = float((pagew_px/2) - (r2mid/scale))

    gd_diagram.draw(format="linear", start=start, end=end, fragments=1, pagesize=(225, pagew_px), xl=(loffset/pagew_px), xr=(roffset/pagew_px) )

    gd_diagram.write(imgfileloc, "PNG")

    #flip for reversed genes
    if centerdstrand == -1:
        os.system("convert -rotate 180 %s %s" % (imgfileloc, imgfileloc))
    return imgfileloc


##########################
# Other utilities        #
##########################

def RGB_to_hex(RGBlist):
    '''
    Convert an RGB color into a HEX string (required for some display functions)
    '''
    n = lambda x: int(x*255)
    RGB256 = [(n(r),n(g),n(b)) for r,g,b in RGBlist]
    colors = ['#%02x%02x%02x' % (r, g, b) for r, g, b in RGB256]
    return colors

def colormap(valuelist):
    '''
    Generate a list of divergent colors for use with labeling SeqFeature objects
    '''
    values = numpy.unique(valuelist)
    N = len(values)
    #we will vary in 2 dimensions, so this is how many steps in each
    perm = int(math.ceil(math.sqrt(N)))
    #need offset, as humans can't tell colors that are unsaturated apart
    H = [(x*1.0/perm) for x in range(perm)]
    S = [(x*1.0/perm)+0.2 for x in range(perm)]
    #we will use this to truncate at correct length
    V = [0.7]*N
    # Create all combinations of our colors.                                                                                                                                                           
    HS = itertools.product(H, S)
    H, S = zip(*HS)
    HSV = zip(H,S,V)
    RGB = [colorsys.hsv_to_rgb(h,s,v) for h, s, v in HSV]
    colorlookup = dict(zip(values, RGB[:N]))
    return colorlookup
